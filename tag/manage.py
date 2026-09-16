"""Administration commands. Passwords are prompted, never command-line arguments."""
import argparse
import getpass
import secrets
from werkzeug.security import generate_password_hash
from .app import app, uid, now, audit
from .db import init_db, execute, one, db


def main():
    parser = argparse.ArgumentParser(description='TAG administration')
    parser.add_argument('command', choices=['init', 'create-staff', 'reset-password', 'disable-account', 'demo', 'prune'])
    parser.add_argument('--email')
    parser.add_argument('--name')
    args = parser.parse_args()
    with app.app_context():
        if args.command == 'init':
            init_db()
            print('Database initialised.')
            return
        if args.command == 'demo':
            if one('SELECT id FROM users LIMIT 1'):
                raise SystemExit('Demo seeding requires an empty database.')
            parent_id, staff_id, child_id = uid(), uid(), uid()
            for user_id, email, name, role in [(staff_id,'school@example.test','Alex Morgan','staff'),(parent_id,'parent@example.test','Jamie Taylor','parent')]:
                password = secrets.token_urlsafe(16)
                execute('INSERT INTO users (id,email,name,role,password,must_change) VALUES (?,?,?,?,?,0)', (user_id,email,name,role,generate_password_hash(password)))
                print(f'{email}: {password}')
            execute('INSERT INTO children VALUES (?,?,?)', (child_id,'Sam Taylor','Willow · Year 4'))
            execute('INSERT INTO guardians VALUES (?,?)', (child_id,parent_id))
            print('Fictional demo accounts created. Keep generated passwords private.')
        elif args.command == 'prune':
            # Explicit administrator action, never silently run against live data.
            execute('DELETE FROM sessions WHERE expires<?', (now(),))
            execute('DELETE FROM throttle WHERE window_start<?', (now()-86400,))
            print('Expired sessions and old rate-limit counters removed.')
        else:
            if not args.email:
                parser.error('--email is required')
            email = args.email.strip().lower()
            user = one('SELECT id FROM users WHERE email=?', (email,))
            if args.command == 'create-staff':
                if user:
                    raise SystemExit('Account already exists.')
                if not args.name or '@' not in email:
                    parser.error('A valid --email and --name are required')
                password = getpass.getpass('Initial password (12+ characters): ')
                if len(password) < 12 or len(password) > 256:
                    raise SystemExit('Password must be 12–256 characters.')
                staff_id = uid()
                execute("INSERT INTO users (id,email,name,role,password,must_change) VALUES (?,?,?,'staff',?,0)", (staff_id,email,args.name,generate_password_hash(password)))
                # New staff can see all unresolved help requests immediately.
                execute('INSERT INTO alert_receipts (alert_id,user_id) SELECT id,? FROM alerts WHERE resolved IS NULL', (staff_id,))
                audit('staff_created',staff_id,'administrator-cli')
            else:
                if not user:
                    raise SystemExit('Account not found.')
                execute('DELETE FROM sessions WHERE user_id=?', (user['id'],))
                if args.command == 'disable-account':
                    execute('UPDATE users SET active=0 WHERE id=?', (user['id'],))
                    audit('account_disabled',user['id'],'administrator-cli')
                else:
                    password = secrets.token_urlsafe(16)
                    execute('UPDATE users SET password=?,must_change=1 WHERE id=?', (generate_password_hash(password),user['id']))
                    audit('password_reset',user['id'],'administrator-cli')
                    print('Temporary password:', password)
            print('Account updated.')
        db().commit()


if __name__ == '__main__':
    main()
