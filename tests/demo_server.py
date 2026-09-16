"""Disposable browser-test server. Credentials travel only over the child process pipe."""
import json
import secrets
import tempfile
from tag.app import create_app
from tag.db import init_db, execute, db
from werkzeug.security import generate_password_hash

with tempfile.TemporaryDirectory() as temp:
    app = create_app({'DATABASE_URL':'sqlite:///'+temp+'/browser.sqlite','PUBLIC_URL':'http://localhost:8765'})
    credentials = {role:secrets.token_urlsafe(20) for role in ['staff','parent']}
    with app.app_context():
        init_db()
        for role, name in [('staff','Alex Morgan'),('parent','Jamie Taylor')]:
            execute('INSERT INTO users (id,email,name,role,password,must_change) VALUES (?,?,?,?,?,0)',
                    (role,role+'@example.test',name,role,generate_password_hash(credentials[role])))
        execute("INSERT INTO children VALUES ('child','Sam Taylor','Willow · Year 4')")
        execute("INSERT INTO guardians VALUES ('child','parent')")
        db().commit()
    print(json.dumps(credentials),flush=True)
    app.run(host='127.0.0.1',port=8765,debug=False,use_reloader=False)
