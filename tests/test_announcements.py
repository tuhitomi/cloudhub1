"""Local only: no real announcements, subscriptions, messages or AWS resources."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import io,json,sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from cloudhub.announcements import Announcements,StaticNoticeWriter,PUBLIC_KEY,notice_id
from cloudhub.notifications import NotificationCenter,settings_key
from cloudhub.service import Service,expected
from cloudhub.store import MemoryStore
from cloudhub.errors import HubError
from cloudhub.portal_api import route
from cloudhub.notification_email import compose
from test_user_notifications import Gateway

class Writer:
    def __init__(self):self.payloads=[];self.failure=False;self.counter=0;self.hook=None
    def token(self):self.counter+=1;return str(self.counter)
    def write(self,payload,current):
        if self.hook:self.hook()
        if self.failure:raise TimeoutError('uncertain S3 response')
        if not current():return None
        self.payloads.append(deepcopy(payload));return {'sha256':'local-fixture'}

class AnnouncementTests(unittest.TestCase):
    def setUp(self):
        self.now=1792640000;self.s=Service(MemoryStore(),clock=lambda:self.now);self.a=Announcements(self.s);self.w=Writer()
        self.body={'title':'Bảo trì thử cục bộ','message':'Không gửi ra AWS.','impact':'Website tạm thời không nhận thao tác.',
            'starts_at':self.now+3600,'ends_at':self.now+7200,'language':'vi','notice_kind':'SCHEDULED'}
    def draft(self,key='create-announcement-key'):
        return self.a.create('admin',key,self.body)
    def publish(self,d=None,email=False,key='publish-announcement-key'):
        d=d or self.draft()
        with patch('cloudhub.notification_email.runtime_gateway',return_value=Mock()):
            p=self.a.preview('admin',d['announcement_id'],{'expected_revision':d['revision'],'send_email':email})
        body={'expected_revision':d['revision'],'preview_id':p['preview_id'],'confirm_publish':True}
        return self.a.publish('admin',d['announcement_id'],key,body),body
    def test_draft_and_preview_do_not_publish_or_mutate_infrastructure(self):
        d=self.draft();self.a.preview('admin',d['announcement_id'],{'expected_revision':1,'send_email':False})
        self.assertEqual(self.s.notifications('alice')['items'],[])
        self.assertEqual(self.s.store.scan_kind('operation'),[]);self.assertIsNone(self.s.store.get('Q#GLOBAL'))
    def test_all_accounts_see_own_receipts_and_other_owners_cannot_mark_them(self):
        d,_=self.publish();self.a.sync_public(self.w)
        one=self.s.notifications('alice')['items'][0];two=self.s.notifications('bob')['items'][0]
        self.assertEqual(one['message'],self.body['message']);self.assertNotEqual(one['notification_id'],two['notification_id'])
        with self.assertRaises(HubError):NotificationCenter(self.s).read('bob',one['notification_id'])
        NotificationCenter(self.s).read('alice',one['notification_id'])
        self.assertEqual(self.s.notifications('alice')['unread_count'],0);self.assertEqual(self.s.notifications('bob')['unread_count'],1)
    def test_preview_expiry_revision_actor_and_single_consumption(self):
        d=self.draft();p=self.a.preview('admin',d['announcement_id'],{'expected_revision':1,'send_email':False})
        body={'expected_revision':1,'preview_id':p['preview_id'],'confirm_publish':True}
        with self.assertRaises(HubError):self.a.publish('other-admin',d['announcement_id'],'other-publish-key',body)
        self.now+=601
        with self.assertRaises(HubError):self.a.publish('admin',d['announcement_id'],'expired-publish-key',body)
        d=self.a.edit('admin',d['announcement_id'],'edit-content-key',{**self.body,'title':'Đã sửa','expected_revision':1})
        with self.assertRaises(HubError):self.a.publish('admin',d['announcement_id'],'changed-publish-key',body)
    def test_accepted_retry_after_preview_expiry_returns_same_operation(self):
        d,body=self.publish();self.now+=1000
        again=self.a.publish('admin',d['announcement_id'],'publish-announcement-key',body)
        self.assertEqual(again['operation_id'],d['operation_id']);self.assertEqual(self.a.state()['generation'],1)
        with self.assertRaises(HubError):self.a.publish('admin',d['announcement_id'],'publish-announcement-key',{**body,'expected_revision':999})
    def test_duplicate_concurrent_publication_is_accepted_once_and_other_draft_waits(self):
        d=self.draft();p=self.a.preview('admin',d['announcement_id'],{'expected_revision':1,'send_email':False})
        body={'expected_revision':1,'preview_id':p['preview_id'],'confirm_publish':True}
        with ThreadPoolExecutor(max_workers=5) as pool:rows=list(pool.map(lambda _:self.a.publish('admin',d['announcement_id'],'publish-concurrent-key',body),range(10)))
        self.assertEqual(len({r['operation_id'] for r in rows}),1);self.assertEqual(self.a.state()['generation'],1)
        other=self.draft('another-draft-key')
        with self.assertRaises(HubError):self.publish(other,key='another-publish-key')
    def test_timeout_never_reports_published_and_automatic_retry_is_bounded(self):
        d,_=self.publish();self.w.failure=True
        for _ in range(4):self.a.sync_public(self.w);self.now+=301
        self.assertEqual(self.a.state()['attempts'],3);self.assertEqual(self.a.state()['status'],'FAILED')
        self.assertEqual(self.a.get(d['announcement_id'])['status'],'QUEUED');self.assertEqual(self.s.notifications('alice')['items'],[])
        self.a.retry_sync('admin',d['announcement_id'],'explicit-retry-key',{'expected_revision':d['revision']})
        self.w.failure=False;self.a.sync_public(self.w)
        self.assertEqual(self.a.state()['status'],'SYNCED')
    def test_dynamodb_numbers_allow_sweep_success_and_failure_logging(self):
        # DynamoDB returns Decimal even for integer generations. Exercise the
        # persisted representation rather than only MemoryStore's native ints.
        from boto3.dynamodb.types import TypeSerializer,TypeDeserializer
        original_get=self.s.store.get;ser=TypeSerializer();des=TypeDeserializer()
        def persisted_get(key):
            row=original_get(key)
            return des.deserialize(ser.serialize(row)) if row is not None else None
        self.publish()
        self.s.store.get=persisted_get
        self.w.failure=True
        failed=self.a.sync_public(self.w)
        self.assertEqual(json.loads(json.dumps(failed))['status'],'PUBLIC_SYNC_FAILED')
        self.now+=301;self.w.failure=False
        synced=self.a.sync_public(self.w)
        self.assertEqual(json.loads(json.dumps(synced))['status'],'SYNCED')
        self.assertIs(type(synced['generation']),int)
        self.assertIsNone(self.a.sync_public(self.w))
    def test_cancel_updates_static_state_before_claiming_withdrawal_complete(self):
        d,_=self.publish();self.a.sync_public(self.w);d=self.a.view(self.a.get(d['announcement_id']))
        self.a.cancel('admin',d['announcement_id'],'cancel-notice-key',{'expected_revision':d['revision'],'confirm_cancel':True})
        self.assertTrue(self.w.payloads[-1]['active']);self.assertEqual(self.a.get(d['announcement_id'])['status'],'CANCEL_PENDING')
        self.a.sync_public(self.w);self.assertFalse(self.w.payloads[-1]['active'])
        self.assertEqual(self.a.get(d['announcement_id'])['status'],'CANCELLED')
        self.assertFalse(self.s.notifications('alice')['history'][0]['current'])
    def test_latest_update_supersedes_old_notice_without_erasing_history(self):
        old,_=self.publish();self.a.sync_public(self.w);self.now+=1
        self.body.update(notice_kind='COMPLETED',title='Đã hoàn tất')
        new,_=self.publish(self.draft('completion-draft-key'),key='completion-publish-key');self.a.sync_public(self.w)
        result=self.s.notifications('alice');self.assertEqual(len(result['items']),1)
        self.assertEqual(result['items'][0]['announcement_id'],new['announcement_id']);self.assertEqual(len(result['history']),2)
    def test_maintenance_email_requires_its_own_opt_in_and_read_receipt_is_preserved(self):
        gateway=Gateway();center=NotificationCenter(self.s)
        for owner,optin in [('alice',True),('bob',False)]:
            identity={'owner_id':owner,'username':owner,'email':owner+'@example.test','email_verified':True}
            center.preferences_update(owner,{'email_enabled':True,'expiry_email':True,'renewal_email':True,'maintenance_email':optin},gateway,identity)
        d,_=self.publish(email=True);self.a.sync_public(self.w)
        n=center.list('alice')['items'][0];center.read('alice',n['notification_id'])
        self.assertEqual(self.a.queue_emails(),1);self.assertEqual(self.a.queue_emails(),0)
        self.assertTrue(self.s.store.get('N#'+n['notification_id'])['read_at'])
        center.drain(gateway,lambda owner,username:{'owner_id':owner,'email':owner+'@example.test','email_verified':True})
        self.assertEqual([r[0] for r in gateway.sends],['alice'])
    def test_old_preference_client_preserves_maintenance_choice_and_new_opt_in_does_not_send_history(self):
        gateway=Gateway();center=NotificationCenter(self.s);identity={'owner_id':'alice','username':'alice','email':'alice@example.test','email_verified':True}
        self.assertFalse(center.preferences('alice')['maintenance_email'])
        body={'email_enabled':True,'expiry_email':True,'renewal_email':True,'maintenance_email':True}
        center.preferences_update('alice',body,gateway,identity)
        center.preferences_update('alice',{k:v for k,v in body.items() if k!='maintenance_email'},gateway,identity)
        self.assertTrue(center.preferences('alice')['maintenance_email'])
        d,_=self.publish(email=True);self.a.sync_public(self.w);self.now+=1
        identity2={**identity,'owner_id':'late','username':'late','email':'late@example.test'}
        center.preferences_update('late',body,gateway,identity2);self.a.queue_emails()
        self.assertIsNone(self.s.store.get('N#'+notice_id('late',d['announcement_id'])))
    def test_non_admin_or_revoked_admin_cannot_access_routes(self):
        args=(self.s,'GET','/admin/announcements',{},'irrelevant-key','alice')
        with self.assertRaises(HubError):route(*args,False,{}, {},lambda x:x)
        with patch('cloudhub.accounts.Accounts') as accounts,patch.dict('os.environ',{'USER_POOL_ID':'local-only'}):
            accounts.return_value.assert_admin=Mock(side_effect=HubError('FORBIDDEN','revoked',403))
            with self.assertRaises(HubError):route(*args,True,{'username':'alice'},{},lambda x:x)
    def test_published_content_is_immutable_and_dates_are_validated(self):
        for body in [{**self.body,'starts_at':True},{**self.body,'ends_at':self.now},{**self.body,'owner_id':'other'},
                     {**self.body,'ends_at':self.body['starts_at']+32*86400}]:
            with self.assertRaises(HubError):self.a.create('admin','invalid-input-key',body)
        d,_=self.publish();self.a.sync_public(self.w)
        with self.assertRaises(HubError):self.a.edit('admin',d['announcement_id'],'edit-after-publish',{**self.body,'expected_revision':d['revision']})
    def test_static_writer_uses_conditional_write_and_never_overwrites_unrelated_content(self):
        from botocore.exceptions import ClientError
        client=Mock();client.put_object.side_effect=[ClientError({'Error':{'Code':'PreconditionFailed'}},'PutObject'),{}]
        client.get_object.return_value={'ETag':'owned-etag','Body':io.BytesIO(b'{"publisher":"cloudhub-maintenance","schema":1}')}
        writer=StaticNoticeWriter(client,'owned-frontend-bucket','133130236086')
        result=writer.write({'publisher':'cloudhub-maintenance','schema':1},lambda:True)
        self.assertEqual(client.put_object.call_args.kwargs['IfMatch'],'owned-etag');self.assertTrue(result['sha256'])
        client.put_object.side_effect=ClientError({'Error':{'Code':'PreconditionFailed'}},'PutObject')
        client.get_object.return_value={'ETag':'foreign','Body':io.BytesIO(b'{"unrelated":true}')}
        with self.assertRaises(ValueError):writer.write({'schema':1},lambda:True)
    def test_all_eight_email_languages_support_notices_without_environment_or_secret(self):
        row={'type':'MAINTENANCE_NOTICE','title':'Local test','message':'A message','impact':'Read only',
            'starts_at':self.now,'ends_at':self.now+60,'notification_id':'notice-local'}
        for language in ['vi','en','ja','ko','zh-Hans','fr','de','es']:
            subject,body=compose(row,language,'https://example.invalid')
            self.assertTrue(subject.isascii());self.assertIn('/maintenance.html',body);self.assertNotIn('undefined',body)
    def test_stale_sweep_cannot_complete_a_new_generation(self):
        d,_=self.publish()
        def supersede():
            state=self.a.state();state.update(generation=state['generation']+1,lease_token='another-worker')
            self.s.store.commit([state],expected(state))
        self.w.hook=supersede
        self.a.sync_public(self.w)
        self.assertEqual(self.a.get(d['announcement_id'])['status'],'QUEUED');self.assertEqual(self.w.payloads,[])

if __name__=='__main__':unittest.main()
