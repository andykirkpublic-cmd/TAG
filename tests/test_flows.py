import os
import tempfile
import unittest
from werkzeug.security import generate_password_hash
from tag.app import create_app, now
from tag.db import init_db, execute, db, one


class PilotTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = create_app({'TESTING':True,'DATABASE_URL':os.getenv('TEST_DATABASE_URL','sqlite:///'+self.tmp.name+'/test.sqlite'),'PUBLIC_URL':'http://localhost:8000'})
        self.ctx = self.app.app_context()
        self.ctx.push()
        init_db()
        for table in ['audit','alert_receipts','alerts','messages','devices','guardians','children','sessions','users','throttle']:
            execute('DELETE FROM '+table)
        for user_id, role in [('staff','staff'),('parent','parent'),('other','parent')]:
            execute('INSERT INTO users (id,email,name,role,password,must_change) VALUES (?,?,?,?,?,0)', (user_id,user_id+'@example.test',user_id,role,generate_password_hash('test-password-long')))
        execute("INSERT INTO children VALUES ('child','Sam','Year 4')")
        execute("INSERT INTO guardians VALUES ('child','parent')")
        db().commit()
        self.staff,self.parent,self.other,self.device = [self.app.test_client() for _ in range(4)]
        self.tokens={}
        for client, name in [(self.staff,'staff'),(self.parent,'parent'),(self.other,'other')]:
            self.assertEqual(self.post(client,'/login',{'email':name+'@example.test','password':'test-password-long'}).status_code,200)
            self.tokens[id(client)] = client.get('/api/me').json['csrf']
        code=self.post(self.staff,'/admin/pair',{'child_id':'child'}).json['code']
        self.assertEqual(self.post(self.device,'/device/pair',{'code':code}).status_code,200)

    def tearDown(self):
        self.ctx.pop()
        self.tmp.cleanup()

    def post(self, client, path, body):
        return client.post('/api'+path,json=body,headers={'Origin':'http://localhost:8000','X-CSRF-Token':self.tokens.get(id(client),'')})

    def message(self, kind='NOTICE', key='key'):
        response=self.post(self.parent,'/messages',{'child_id':'child','kind':kind,'body':'Grandad is collecting you.','request_key':key})
        self.assertEqual(response.status_code,201)
        return response.json['id']

    def test_notice_delivery_and_acknowledgement(self):
        message_id=self.message()
        self.assertIsNone(one('SELECT delivered FROM messages WHERE id=?',(message_id,))['delivered'])
        self.assertEqual(self.device.get('/api/device/state').json['message']['id'],message_id)
        self.assertIsNone(one('SELECT delivered FROM messages WHERE id=?',(message_id,))['delivered'])
        self.post(self.device,'/device/delivered',{'id':message_id})
        self.assertIsNotNone(one('SELECT delivered FROM messages WHERE id=?',(message_id,))['delivered'])
        self.assertEqual(self.post(self.device,'/device/respond',{'id':message_id,'response':'NO'}).status_code,400)
        self.assertEqual(self.post(self.device,'/device/respond',{'id':message_id,'response':'ACK'}).status_code,200)
        self.assertIsNone(self.device.get('/api/device/state').json['message'])

    def test_question_response_cannot_be_changed(self):
        mid=self.message('QUESTION')
        self.assertEqual(self.post(self.device,'/device/respond',{'id':mid,'response':'ACK'}).status_code,400)
        for _ in range(2):
            self.assertEqual(self.post(self.device,'/device/respond',{'id':mid,'response':'YES'}).status_code,200)
        self.assertEqual(self.post(self.device,'/device/respond',{'id':mid,'response':'NO'}).status_code,409)

    def test_family_isolation_and_device_scope(self):
        self.message()
        self.assertEqual(self.other.get('/api/dashboard').json['children'],[])
        self.assertEqual(self.post(self.other,'/messages',{'child_id':'child','kind':'NOTICE','body':'x','request_key':'other'}).status_code,404)
        self.assertEqual(self.post(self.parent,'/admin/pair',{'child_id':'child'}).status_code,403)
        self.assertEqual(self.device.get('/api/dashboard').status_code,401)
        self.assertEqual(self.parent.get('/api/device/state').status_code,401)

    def test_help_reaches_both_and_is_idempotent(self):
        a=self.post(self.device,'/device/help',{}).json['id']
        self.assertEqual(self.post(self.device,'/device/help',{}).json['id'],a)
        for client in [self.staff,self.parent]:
            self.assertEqual(client.get('/api/dashboard').json['alerts'][0]['id'],a)
        self.assertEqual(self.other.get('/api/dashboard').json['alerts'],[])
        self.post(self.parent,f'/alerts/{a}/seen',{})
        self.assertIsNone(self.staff.get('/api/dashboard').json['alerts'][0]['seen'])
        self.assertEqual(self.post(self.parent,f'/alerts/{a}/resolve',{}).status_code,403)
        self.assertEqual(self.post(self.staff,f'/alerts/{a}/resolve',{}).status_code,200)
        self.assertIsNone(self.device.get('/api/device/state').json['alert'])

    def test_expired_message_cannot_be_answered(self):
        mid=self.message()
        execute('UPDATE messages SET expires=? WHERE id=?',(now()-1,mid));db().commit()
        self.assertIsNone(self.device.get('/api/device/state').json['message'])
        self.assertEqual(self.post(self.device,'/device/respond',{'id':mid,'response':'ACK'}).status_code,409)

    def test_pairing_one_use_and_revocation(self):
        code=self.post(self.staff,'/admin/pair',{'child_id':'child'}).json['code']
        replacement=self.app.test_client()
        self.assertEqual(self.post(replacement,'/device/pair',{'code':code}).status_code,200)
        self.assertEqual(self.post(replacement,'/device/pair',{'code':code}).status_code,400)
        self.assertEqual(self.device.get('/api/device/state').status_code,401)
        self.post(self.staff,'/admin/revoke-device',{'child_id':'child'})
        self.assertEqual(replacement.get('/api/device/state').status_code,401)

    def test_csrf_origin_and_unauthenticated_requests(self):
        self.assertEqual(self.parent.post('/api/logout',json={},headers={'Origin':'http://localhost:8000'}).status_code,403)
        self.assertEqual(self.parent.post('/api/logout',json={},headers={'Origin':'https://evil.test','X-CSRF-Token':self.tokens[id(self.parent)]}).status_code,403)
        self.assertEqual(self.app.test_client().get('/api/dashboard').status_code,401)

    def test_duplicate_send_and_validation(self):
        mid=self.message()
        result=self.post(self.parent,'/messages',{'child_id':'child','kind':'NOTICE','body':'same','request_key':'key'})
        self.assertEqual(result.json['id'],mid)
        self.assertEqual(one('SELECT COUNT(*) AS n FROM messages')['n'],1)
        self.assertEqual(self.post(self.parent,'/messages',{'child_id':'child','kind':'OTHER','body':'x','request_key':'new'}).status_code,400)

    def test_parent_onboarding_and_password_rotation(self):
        created=self.post(self.staff,'/admin/parents',{'name':'New Parent','email':'new@example.test'}).json
        client=self.app.test_client()
        self.post(client,'/login',{'email':'new@example.test','password':created['temporary_password']})
        self.tokens[id(client)]=client.get('/api/me').json['csrf']
        self.assertEqual(client.get('/api/dashboard').status_code,403)
        self.assertEqual(self.post(client,'/password',{'current':created['temporary_password'],'password':'my-new-long-password'}).status_code,200)
        self.assertEqual(client.get('/api/dashboard').status_code,200)

    def test_rate_limit_pairing(self):
        for _ in range(9):self.post(self.device,'/device/pair',{'code':'00000000'})
        self.assertEqual(self.post(self.device,'/device/pair',{'code':'00000000'}).status_code,429)


if __name__ == '__main__':
    unittest.main()
