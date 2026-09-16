import hashlib
import os
import secrets
import time
import uuid
from functools import wraps
from flask import Flask, request, jsonify, g, make_response, render_template, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from .db import db, execute, one, rows, init_db, close_db


def now():
    return int(time.time())


def uid():
    return str(uuid.uuid4())


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def audit(action, target, actor=None):
    execute('INSERT INTO audit VALUES (?,?,?,?,?)',
            (uid(), actor or g.user['id'], action, target, now()))


def required(role=None):
    def decorate(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not g.user:
                abort(401, 'Please sign in.')
            if role and g.user['role'] != role:
                abort(403, 'School staff access required.')
            if g.user['must_change'] and request.path not in ('/api/password', '/api/logout', '/api/me'):
                abort(403, 'Please change your temporary password first.')
            return fn(*args, **kwargs)
        return wrapped
    return decorate


def child_access(child_id):
    child = one('SELECT * FROM children WHERE id=?', (child_id,))
    if not child or (g.user['role'] == 'parent' and not one(
            'SELECT * FROM guardians WHERE child_id=? AND user_id=?', (child_id, g.user['id']))):
        abort(404, 'Child not found.')
    return child


def payload():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        abort(400, 'A JSON object is required.')
    return data


def field(data, key, limit=120):
    value = data.get(key)
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        abort(400, f'{key} must contain 1–{limit} characters.')
    return value.strip()


def throttle(key, limit=10, window=900):
    key = digest(key)
    execute('INSERT INTO throttle VALUES (?,1,?) ON CONFLICT(key) DO UPDATE SET '
            'attempts=CASE WHEN throttle.window_start<? THEN 1 ELSE throttle.attempts+1 END, '
            'window_start=CASE WHEN throttle.window_start<? THEN ? ELSE throttle.window_start END',
            (key, now(), now()-window, now()-window, now()))
    count = one('SELECT attempts FROM throttle WHERE key=?', (key,))['attempts']
    db().commit()
    if count > limit:
        abort(429, 'Too many attempts. Please try again later.')


def create_app(config=None):
    app = Flask(__name__)
    app.config.update(DATABASE_URL=os.getenv('DATABASE_URL', 'sqlite:///data/tag.sqlite'),
                      PUBLIC_URL=os.getenv('PUBLIC_URL', 'http://localhost:8000').rstrip('/'),
                      SCHOOL_NAME=os.getenv('SCHOOL_NAME', 'TAG Pilot School'),
                      MAX_CONTENT_LENGTH=16384)
    if config:
        app.config.update(config)
    # Enable only behind the single Caddy proxy supplied with this repository.
    if os.getenv('TRUST_PROXY') == '1':
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.teardown_appcontext(close_db)

    @app.before_request
    def authenticate():
        g.user = None
        g.session = None
        if request.path.startswith('/api/'):
            token = request.cookies.get('tag_session', '')
            if token:
                session = one('SELECT * FROM sessions WHERE token=? AND expires>?', (digest(token), now()))
                if session:
                    g.user = one('SELECT id,email,name,role,must_change FROM users WHERE id=? AND active=1',
                                 (session['user_id'],))
                    g.session = session
            if request.method not in ('GET', 'HEAD', 'OPTIONS'):
                if request.headers.get('Origin') != app.config['PUBLIC_URL']:
                    abort(403, 'Request origin rejected.')
                if g.user and request.path not in ('/api/login', '/api/device/pair') and not request.path.startswith('/api/device/'):
                    if not secrets.compare_digest(request.headers.get('X-CSRF-Token', ''), g.session['csrf']):
                        abort(403, 'Please refresh the page and try again.')

    @app.after_request
    def security(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        if request.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.errorhandler(400)
    @app.errorhandler(401)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(409)
    @app.errorhandler(413)
    @app.errorhandler(429)
    def error(err):
        return jsonify(error=err.description), err.code

    @app.get('/')
    @app.get('/device')
    def index():
        return render_template('index.html', school=app.config['SCHOOL_NAME'])

    @app.get('/healthz')
    def health():
        one('SELECT 1 AS ok')
        return jsonify(status='ok')

    @app.get('/sw.js')
    def service_worker():
        response = app.send_static_file('sw.js')
        response.headers['Cache-Control'] = 'no-cache'
        return response

    def set_cookie(response, name, token, max_age):
        response.set_cookie(name, token, max_age=max_age, httponly=True,
                            secure=app.config['PUBLIC_URL'].startswith('https://'), samesite='Strict')

    @app.post('/api/login')
    def login():
        data = payload()
        email = field(data, 'email', 254).lower()
        password = field(data, 'password', 256)
        throttle('login-ip:'+str(request.remote_addr), 40)
        throttle('login-email:'+email)
        user = one('SELECT * FROM users WHERE email=? AND active=1', (email,))
        # Always verify a hash to reduce account enumeration through timing.
        if 'DUMMY_HASH' not in app.config:
            app.config['DUMMY_HASH'] = generate_password_hash(secrets.token_urlsafe(24))
        fallback = app.config['DUMMY_HASH']
        if not check_password_hash(user['password'] if user else fallback, password) or not user:
            abort(401, 'Email or password not recognised.')
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        execute('DELETE FROM sessions WHERE expires<?', (now(),))
        execute('INSERT INTO sessions VALUES (?,?,?,?)', (digest(token), user['id'], csrf, now()+43200))
        audit('login', user['id'], user['id'])
        db().commit()
        response = jsonify(ok=True)
        set_cookie(response, 'tag_session', token, 43200)
        return response

    @app.get('/api/me')
    @required()
    def me():
        return jsonify(user=g.user, csrf=g.session['csrf'], school=app.config['SCHOOL_NAME'])

    @app.post('/api/logout')
    @required()
    def logout():
        execute('DELETE FROM sessions WHERE token=?', (g.session['token'],))
        db().commit()
        response = jsonify(ok=True)
        response.delete_cookie('tag_session')
        return response

    @app.post('/api/password')
    @required()
    def password():
        data = payload()
        old, new = field(data, 'current', 256), field(data, 'password', 256)
        throttle('password:'+g.user['id'])
        user = one('SELECT password FROM users WHERE id=?', (g.user['id'],))
        if not check_password_hash(user['password'], old):
            abort(400, 'Current password is incorrect.')
        if len(new) < 12 or new == old:
            abort(400, 'Use a different password of at least 12 characters.')
        execute('UPDATE users SET password=?,must_change=0 WHERE id=?', (generate_password_hash(new), g.user['id']))
        execute('DELETE FROM sessions WHERE user_id=? AND token<>?', (g.user['id'], g.session['token']))
        audit('password_changed', g.user['id'])
        db().commit()
        return jsonify(ok=True)

    @app.get('/api/dashboard')
    @required()
    def dashboard():
        if g.user['role'] == 'staff':
            children = rows('SELECT * FROM children ORDER BY name')
        else:
            children = rows('SELECT c.* FROM children c JOIN guardians g ON g.child_id=c.id WHERE g.user_id=? ORDER BY c.name', (g.user['id'],))
        for child in children:
            child['device'] = one('SELECT id,last_seen FROM devices WHERE child_id=?', (child['id'],))
            child['messages'] = rows('SELECT m.*,u.name AS sender FROM messages m JOIN users u ON u.id=m.sender_id WHERE child_id=? ORDER BY created DESC,id DESC LIMIT 50', (child['id'],))
        alerts = rows('SELECT a.*,c.name AS child_name,r.seen,u.name AS resolved_name FROM alerts a '
                      'JOIN alert_receipts r ON r.alert_id=a.id JOIN children c ON c.id=a.child_id '
                      'LEFT JOIN users u ON u.id=a.resolved_by WHERE r.user_id=? ORDER BY a.created DESC LIMIT 100', (g.user['id'],))
        return jsonify(children=children, alerts=alerts, server_time=now())

    @app.post('/api/messages')
    @required()
    def send_message():
        data = payload()
        child_id = field(data, 'child_id')
        child_access(child_id)
        kind, body, key = field(data, 'kind'), field(data, 'body', 240), field(data, 'request_key')
        if kind not in ('NOTICE', 'QUESTION'):
            abort(400, 'Choose NOTICE or QUESTION.')
        existing = one('SELECT id FROM messages WHERE sender_id=? AND request_key=?', (g.user['id'], key))
        if existing:
            return jsonify(id=existing['id'])
        throttle('messages:'+g.user['id'], 30, 60)
        message_id = uid()
        execute('INSERT INTO messages (id,child_id,sender_id,kind,body,created,expires,request_key) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(sender_id,request_key) DO NOTHING',
                (message_id, child_id, g.user['id'], kind, body, now(), now()+86400, key))
        saved = one('SELECT id FROM messages WHERE sender_id=? AND request_key=?', (g.user['id'], key))
        audit('message_sent', saved['id'])
        db().commit()
        return jsonify(id=saved['id']), 201

    @app.get('/api/admin/parents')
    @required('staff')
    def parents():
        return jsonify(parents=rows("SELECT id,name,email FROM users WHERE role='parent' AND active=1 ORDER BY name"))

    @app.post('/api/admin/parents')
    @required('staff')
    def add_parent():
        data = payload()
        name, email = field(data, 'name'), field(data, 'email', 254).lower()
        if '@' not in email or '.' not in email.rsplit('@', 1)[-1]:
            abort(400, 'Enter a valid email address.')
        user_id, temp = uid(), secrets.token_urlsafe(16)
        inserted = execute("INSERT INTO users (id,email,name,role,password) VALUES (?,?,?,'parent',?) ON CONFLICT(email) DO NOTHING",
                           (user_id, email, name, generate_password_hash(temp))).rowcount
        if not inserted:
            abort(409, 'That email address already has an account.')
        audit('parent_created', user_id)
        db().commit()
        return jsonify(id=user_id, temporary_password=temp), 201

    @app.post('/api/admin/children')
    @required('staff')
    def add_child():
        data = payload()
        name, class_name, parent_id = field(data, 'name'), field(data, 'class_name'), field(data, 'parent_id')
        if not one("SELECT id FROM users WHERE id=? AND role='parent' AND active=1", (parent_id,)):
            abort(400, 'Choose an existing parent account.')
        child_id = uid()
        execute('INSERT INTO children VALUES (?,?,?)', (child_id, name, class_name))
        execute('INSERT INTO guardians VALUES (?,?)', (child_id, parent_id))
        audit('child_created', child_id)
        db().commit()
        return jsonify(id=child_id), 201

    @app.post('/api/admin/guardians')
    @required('staff')
    def add_guardian():
        data = payload()
        child_id, parent_id = field(data, 'child_id'), field(data, 'parent_id')
        child_access(child_id)
        if not one("SELECT id FROM users WHERE id=? AND role='parent' AND active=1", (parent_id,)):
            abort(400, 'Choose an existing parent account.')
        execute('INSERT INTO guardians VALUES (?,?) ON CONFLICT DO NOTHING', (child_id, parent_id))
        # A newly linked guardian also receives any outstanding help request.
        for alert in rows('SELECT id FROM alerts WHERE child_id=? AND resolved IS NULL', (child_id,)):
            execute('INSERT INTO alert_receipts (alert_id,user_id) VALUES (?,?) ON CONFLICT DO NOTHING', (alert['id'], parent_id))
        audit('guardian_linked', child_id)
        db().commit()
        return jsonify(ok=True)

    @app.post('/api/admin/pair')
    @required('staff')
    def pair_code():
        child_id = field(payload(), 'child_id')
        child_access(child_id)
        code = str(secrets.randbelow(90000000)+10000000)
        execute('INSERT INTO devices (id,child_id,pairing_hash,pairing_expires) VALUES (?,?,?,?) '
                'ON CONFLICT(child_id) DO UPDATE SET pairing_hash=excluded.pairing_hash,pairing_expires=excluded.pairing_expires',
                (uid(), child_id, digest(code), now()+600))
        audit('pairing_created', child_id)
        db().commit()
        return jsonify(code=code, expires_in=600)

    @app.post('/api/admin/revoke-device')
    @required('staff')
    def revoke_device():
        child_id = field(payload(), 'child_id')
        child_access(child_id)
        execute('UPDATE devices SET token=NULL,pairing_hash=NULL,pairing_expires=NULL,last_seen=NULL WHERE child_id=?', (child_id,))
        audit('device_revoked', child_id)
        db().commit()
        return jsonify(ok=True)

    @app.post('/api/device/pair')
    def pair():
        throttle('pair:'+str(request.remote_addr), 10)
        code = field(payload(), 'code', 8)
        token = secrets.token_urlsafe(32)
        device = one('UPDATE devices SET token=?,pairing_hash=NULL,pairing_expires=NULL,last_seen=? '
                     'WHERE pairing_hash=? AND pairing_expires>? RETURNING id', (digest(token), now(), digest(code), now()))
        if not device:
            abort(400, 'Pairing code is invalid or has expired.')
        audit('device_paired', device['id'], device['id'])
        db().commit()
        response = jsonify(ok=True)
        set_cookie(response, 'tag_device', token, 86400*365)
        return response

    def device_auth():
        token = request.cookies.get('tag_device', '')
        device = one('SELECT d.*,c.name FROM devices d JOIN children c ON c.id=d.child_id WHERE d.token=?', (digest(token),))
        if not device:
            abort(401, 'Ask school staff for a pairing code.')
        return device

    @app.get('/api/device/state')
    def device_state():
        device = device_auth()
        execute('UPDATE devices SET last_seen=? WHERE id=?', (now(), device['id']))
        message = one('SELECT id,kind,body,created,expires FROM messages WHERE child_id=? AND response IS NULL AND expires>? ORDER BY created,id LIMIT 1', (device['child_id'], now()))
        alert = one('SELECT id,created FROM alerts WHERE child_id=? AND resolved IS NULL', (device['child_id'],))
        db().commit()
        return jsonify(name=device['name'], message=message, alert=alert, server_time=now())

    @app.post('/api/device/delivered')
    def delivered():
        device = device_auth()
        message_id = field(payload(), 'id')
        execute('UPDATE messages SET delivered=COALESCE(delivered,?) WHERE id=? AND child_id=? AND expires>?', (now(), message_id, device['child_id'], now()))
        db().commit()
        return jsonify(ok=True)

    @app.post('/api/device/respond')
    def respond():
        device = device_auth()
        data = payload()
        message_id, response = field(data, 'id'), field(data, 'response')
        message = one('SELECT * FROM messages WHERE id=? AND child_id=?', (message_id, device['child_id']))
        if not message:
            abort(404, 'Message not found.')
        if response not in (('ACK',) if message['kind'] == 'NOTICE' else ('YES','NO')):
            abort(400, 'That response is not available for this message.')
        if message['response']:
            if message['response'] != response:
                abort(409, 'This message already has a different response.')
            return jsonify(ok=True)
        if message['expires'] <= now():
            abort(409, 'This message has expired.')
        changed = execute('UPDATE messages SET response=?,responded=?,delivered=COALESCE(delivered,?) WHERE id=? AND response IS NULL', (response, now(), now(), message_id)).rowcount
        if not changed:
            abort(409, 'This message was already answered. Refresh the device.')
        audit('device_response', message_id, device['id'])
        db().commit()
        return jsonify(ok=True)

    @app.post('/api/device/help')
    def help_request():
        device = device_auth()
        throttle('help:'+device['id'], 10, 60)
        alert_id = uid()
        execute('INSERT INTO alerts (id,child_id,created) VALUES (?,?,?) ON CONFLICT DO NOTHING', (alert_id, device['child_id'], now()))
        alert_id = one('SELECT id FROM alerts WHERE child_id=? AND resolved IS NULL', (device['child_id'],))['id']
        recipients = rows("SELECT id FROM users WHERE active=1 AND (role='staff' OR id IN (SELECT user_id FROM guardians WHERE child_id=?))", (device['child_id'],))
        for user in recipients:
            execute('INSERT INTO alert_receipts (alert_id,user_id) VALUES (?,?) ON CONFLICT DO NOTHING', (alert_id, user['id']))
        audit('help_requested', alert_id, device['id'])
        db().commit()
        return jsonify(id=alert_id), 201

    @app.post('/api/alerts/<alert_id>/seen')
    @required()
    def see_alert(alert_id):
        if not execute('UPDATE alert_receipts SET seen=COALESCE(seen,?) WHERE alert_id=? AND user_id=?', (now(), alert_id, g.user['id'])).rowcount:
            abort(404, 'Alert not found.')
        db().commit()
        return jsonify(ok=True)

    @app.post('/api/alerts/<alert_id>/resolve')
    @required('staff')
    def resolve_alert(alert_id):
        if not one('SELECT id FROM alerts WHERE id=?', (alert_id,)):
            abort(404, 'Alert not found.')
        execute('UPDATE alerts SET resolved=?,resolved_by=? WHERE id=? AND resolved IS NULL', (now(), g.user['id'], alert_id))
        audit('help_resolved', alert_id)
        db().commit()
        return jsonify(ok=True)

    return app


app = create_app()
