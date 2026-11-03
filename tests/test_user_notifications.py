"""Notification/consent/outbox risk checks. LOCAL only; no AWS calls or emails."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from cloudhub.notifications import NotificationCenter, notice, settings_key
from cloudhub.notification_email import SnsEmail, compose
from cloudhub.service import Service
from cloudhub.store import MemoryStore
from cloudhub.cost import Estimator
from cloudhub.errors import HubError
from cloudhub.worker import Worker
from cloudhub.portal_api import route
from test_domain import RATES, Driver


class Gateway:
    def __init__(self):
        self.configures=0;self.sends=[];self.counter=0;self.failure=False;self.pending=False;self.on_configure=None
    def token(self):
        self.counter+=1;return str(self.counter)
    def configure(self, owner, address, allow_subscribe=True):
        self.configures+=1
        if self.on_configure:self.on_configure()
        return {'email_status':'PENDING_CONFIRMATION','masked_email':'a***@example.test'}
    def check(self,owner,address):
        return {'email_status':'CONFIRMED','masked_email':'a***@example.test'}
    def send(self,owner,address,row,locale,predicate):
        if not predicate():return {'email_status':'SKIPPED_STALE'}
        if self.failure:raise TimeoutError('Uncertain provider response')
        if self.pending:return {'email_status':'PENDING'}
        self.sends.append((owner,address,row['notification_id']))
        return {'email_status':'PUBLISHED','email_message_id':'local-fixture'}


class NotificationTests(unittest.TestCase):
    def test_native_route_patch_adds_scoped_lambda_invocation_and_is_repeatable(self):
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
        from notification_infra import extend_native_routes,ROUTES
        example={'security':[{'CognitoJwt':['cloudhub/use']}],'x-amazon-apigateway-integration':{'type':'aws_proxy'},'responses':{}}
        template={'Resources':{'ApiFunction':{'Type':'AWS::Lambda::Function'},
            'HttpApi':{'Properties':{'Body':{'paths':{'/notifications':{'get':example}}}}},
            'HttpApiApiGatewayDefaultStage':{'Properties':{'RouteSettings':{'GET /unrelated':{'ThrottlingRateLimit':1}}}}}}
        first=json.dumps(extend_native_routes(template),sort_keys=True)
        self.assertEqual(json.dumps(extend_native_routes(template),sort_keys=True),first)
        resources=template['Resources']
        for index,(method,path) in enumerate(ROUTES):
            props=resources['UserNotificationInvoke'+str(index)]['Properties']
            self.assertEqual(props['Principal'],'apigateway.amazonaws.com')
            self.assertEqual(props['SourceAccount'],{'Ref':'AWS::AccountId'})
            self.assertTrue(props['SourceArn']['Fn::Sub'].endswith('/*/'+method+path.replace('{notification_id}','*')))
            self.assertEqual(resources['HttpApi']['Properties']['Body']['paths'][path][method.lower()]['security'],example['security'])
        self.assertEqual(resources['HttpApiApiGatewayDefaultStage']['Properties']['RouteSettings']['GET /unrelated'],{'ThrottlingRateLimit':1})
    def test_email_infrastructure_is_default_off_scoped_and_routes_require_jwt(self):
        root=Path(__file__).resolve().parents[1]
        template=json.loads((root/'infra/control-plane.json').read_text())
        self.assertEqual(template['Parameters']['UserNotificationEmailEnabled']['Default'],'false')
        for name in ['UserEmailApiPolicy','UserEmailSweepPolicy']:
            policy=template['Resources'][name]
            self.assertEqual(policy['Condition'],'UserNotificationEmailOn')
            for statement in policy['Properties']['PolicyDocument']['Statement']:
                self.assertNotEqual(statement['Resource'],'*')
                actions=statement['Action'] if isinstance(statement['Action'],list) else [statement['Action']]
                self.assertFalse(set(actions)&{'sns:DeleteTopic','sns:SetTopicAttributes','sns:ConfirmSubscription','sns:*','iam:*'})
        events=template['Resources']['ApiFunction']['Properties']['Events']
        routes=[v for k,v in events.items() if k.startswith('UserNotificationRoute')]
        self.assertEqual(len(routes),4)
        self.assertTrue(all(v['Properties']['ApiId']=={'Ref':'HttpApi'} for v in routes))
        self.assertTrue(template['Resources']['HttpApi']['Properties']['Auth']['DefaultAuthorizer'])

    def setUp(self):
        self.now=1000;self.store=MemoryStore();self.driver=Driver()
        self.s=Service(self.store,clock=lambda:self.now,estimator=Estimator(RATES),verified={'T01'},
                       budget_milliusd=100000,require_quotes=False)
        self.worker=Worker(self.s,self.driver);self.center=NotificationCenter(self.s);self.gateway=Gateway()
        self.identity={'owner_id':'alice','username':'alice','email':'alice@example.test','email_verified':True}
        self.body={'email_enabled':True,'expiry_email':True,'renewal_email':True}
    def ready(self):
        op=self.s.create('alice','createkey',{'template_id':'T01','duration_hours':1})
        for _ in range(12):
            if self.worker.tick(op['operation_id'])['done']:break
        return self.store.get('E#'+op['environment_id'])
    def optin(self):
        return self.center.preferences_update('alice',self.body,self.gateway,self.identity)
    def reminder(self):
        env=self.ready();self.now=env['deadline']-600;self.optin()
        self.s.remind(env['environment_id']);return env
    def lookup(self,owner,username):
        return self.identity
    def test_default_email_is_off_and_arbitrary_address_or_role_is_rejected(self):
        self.assertFalse(self.center.preferences('alice')['email_enabled'])
        for body in ({**self.body,'email':'other@example.test'},{**self.body,'role':'admin'},{**self.body,'email_enabled':1}):
            with self.assertRaises(HubError):self.center.preferences_update('alice',body,self.gateway,self.identity)
        with self.assertRaises(HubError):self.center.preferences_update('alice',self.body,None,self.identity)
        with self.assertRaises(HubError):self.center.preferences_update('bob',self.body,self.gateway,self.identity)
    def test_http_read_route_enforces_owner_and_rejects_mutation_payload(self):
        env=self.ready();self.now=env['deadline']-600;self.s.remind(env['environment_id'])
        nid=self.s.notifications('alice')['items'][0]['notification_id']
        args=(self.s,'POST','/notifications/'+nid+'/read')
        for owner,body in [('bob',{}),('alice',{'owner_id':'alice'})]:
            with self.assertRaises(HubError):route(*args,body,'key',owner,False,{}, {},lambda x:x)
        result,status=route(*args,{},'key','alice',False,{}, {},lambda x:x)
        self.assertEqual(status,200);self.assertEqual(result['read_at'],self.now)
        self.assertEqual(self.store.get(env['pk'])['deadline'],env['deadline'])
    def test_http_preferences_cannot_enable_email_without_verified_server_identity(self):
        with patch('cloudhub.notification_email.runtime_gateway',return_value=self.gateway):
            for identity in (None,dict(self.identity,owner_id='bob'),dict(self.identity,email_verified=False)):
                with self.assertRaises(HubError):route(self.s,'POST','/account/notification-preferences',self.body,'key','alice',False,{}, {},lambda x:x,identity)
            result,status=route(self.s,'POST','/account/notification-preferences',self.body,'key','alice',False,{}, {},lambda x:x,self.identity)
            self.assertEqual(status,200);self.assertEqual(result['email_status'],'PENDING_CONFIRMATION')
    def test_reminder_is_deduplicated_read_is_owned_and_idempotent(self):
        env=self.ready();self.now=env['deadline']-600
        with ThreadPoolExecutor(max_workers=8) as pool:rows=list(pool.map(lambda _:self.s.remind(env['environment_id']),range(16)))
        self.assertEqual(sum(row is not None for row in rows),1)
        nid=self.s.notifications('alice')['items'][0]['notification_id']
        with self.assertRaises(HubError):self.center.read('bob',nid)
        first=self.center.read('alice',nid);self.now+=1
        self.assertEqual(self.center.read('alice',nid)['read_at'],first['read_at'])
        self.assertEqual(self.s.notifications('alice')['unread_count'],0)
        self.assertEqual(self.s.notifications('bob')['history'],[])
    def test_immediate_preview_read_materializes_without_get_writing(self):
        env=self.ready();self.now=env['deadline']-600
        result=self.s.notifications('alice');self.assertEqual(self.store.scan_kind('notification'),[])
        self.center.read('alice',result['items'][0]['notification_id'])
        self.assertEqual(len(self.store.scan_kind('notification')),1)
    def test_renew_preserves_history_and_suppresses_old_deadline_email(self):
        env=self.reminder();oid=self.s.renew('alice',env['environment_id'],'renewkey',{'minutes':60,'confirmed':True})['operation_id']
        self.assertEqual(self.s.notifications('alice')['items'],[])
        self.assertFalse(self.s.notifications('alice')['history'][0]['current'])
        self.center.drain(self.gateway,self.lookup)
        self.assertEqual(self.gateway.sends,[])
        self.assertEqual(self.store.scan_kind('notification')[0]['email_status'],'SKIPPED_STALE')
        self.worker.tick(oid)
        notices=[x for x in self.s.notifications('alice')['items'] if x['type']=='RENEWAL_SUCCEEDED']
        self.assertEqual(len(notices),1)
        self.assertEqual(notices[0]['operation_id'],oid)
    def test_schedule_failure_reports_pending_not_false_renewal_success(self):
        env=self.reminder();op=self.s.renew('alice',env['environment_id'],'renewkey',{'minutes':60,'confirmed':True})
        self.driver.schedule=lambda _:(_ for _ in ()).throw(HubError('SDK_FAILED','fixture'))
        self.worker.tick(op['operation_id'])
        kinds={r['type'] for r in self.s.notifications('alice')['items']}
        self.assertIn('RENEWAL_SYNC_PENDING',kinds);self.assertNotIn('RENEWAL_SUCCEEDED',kinds)
        self.assertGreater(self.store.get(env['pk'])['deadline'],env['deadline'])
    def test_continuous_suppresses_old_reminder(self):
        env=self.reminder();fresh=self.store.get(env['pk']);fresh.update(deadline=None,operating_policy={
            'mode':'CONTINUOUS','period_minutes':None,'ending_policy':'BACKUP_RETIRE','budget_limit_milliusd':None,'confirmed':True})
        self.s.save(fresh);self.center.drain(self.gateway,self.lookup)
        self.assertEqual(self.gateway.sends,[])
    def test_duplicate_sweeps_publish_once_at_application_level(self):
        self.reminder()
        with ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(lambda _:self.center.drain(self.gateway,self.lookup),range(16)))
        self.assertEqual(len(self.gateway.sends),1)
        self.assertEqual(self.store.scan_kind('notification')[0]['email_status'],'PUBLISHED')
        rendered=json.dumps(self.s.notifications('alice'))
        for private in ['alice@example.test','email_token','email_message_id','setup_token']:
            self.assertNotIn(private,rendered)
    def test_unknown_publish_outcome_and_expired_lease_are_not_resent(self):
        self.reminder();self.gateway.failure=True
        self.center.drain(self.gateway,self.lookup);self.gateway.failure=False;self.center.drain(self.gateway,self.lookup)
        self.assertEqual(self.gateway.sends,[])
        row=self.store.scan_kind('notification')[0];self.assertEqual(row['email_status'],'UNKNOWN')
        row.update(email_status='SENDING',email_lease_until=self.now-1);self.s.save(row)
        self.center.drain(self.gateway,self.lookup)
        self.assertEqual(self.store.get(row['pk'])['email_status'],'UNKNOWN')
    def test_optout_or_changed_verified_address_prevents_dispatch(self):
        self.reminder();self.center.preferences_update('alice',{**self.body,'email_enabled':False},self.gateway,self.identity)
        self.center.drain(self.gateway,self.lookup);self.assertEqual(self.gateway.sends,[])
        row=self.store.scan_kind('notification')[0];row['email_status']='PENDING';self.s.save(row);self.optin()
        changed={**self.identity,'email':'changed@example.test'}
        self.center.drain(self.gateway,lambda *_:changed)
        self.assertEqual(self.store.get(row['pk'])['email_status'],'SKIPPED_ADDRESS_CHANGED')
    def test_repeated_optin_does_not_resend_setup_and_optout_wins_inflight(self):
        self.optin();self.optin();self.assertEqual(self.gateway.configures,1)
        self.center.preferences_update('alice',{**self.body,'email_enabled':False},self.gateway,self.identity)
        self.gateway.on_configure=lambda:self.center.preferences_update('alice',{**self.body,'email_enabled':False},self.gateway,self.identity)
        self.optin();self.assertFalse(self.center.preferences('alice')['email_enabled'])
    def test_unconfirmed_delivery_is_pending_and_does_not_claim_inbox_delivery(self):
        self.reminder();self.gateway.pending=True;self.center.drain(self.gateway,self.lookup)
        row=self.store.scan_kind('notification')[0];self.assertEqual(row['email_status'],'PENDING')
        self.assertEqual(row['email_attempt_after'],self.now+300)
        self.center.drain(self.gateway,self.lookup);self.assertEqual(self.gateway.sends,[])
    def test_old_clients_do_not_mislabel_new_success_notifications(self):
        env=self.ready();row=notice(self.s,env,'RENEWAL_SUCCEEDED','notice-test');self.s.save(row)
        old,_=route(self.s,'GET','/notifications',{},None,'alice',False,{}, {}, lambda r:r)
        new,_=route(self.s,'GET','/notifications',{},None,'alice',False,{}, {'schema':'2'},lambda r:r)
        self.assertEqual(old['items'],[]);self.assertEqual(new['items'][0]['type'],'RENEWAL_SUCCEEDED')
    def test_email_subject_and_body_locales_are_safe_and_plaintext(self):
        env=self.ready();row=notice(self.s,env,'EXPIRY_SOON','notice-test')
        for locale in ('vi','en','ja','ko','zh-Hans','fr','de','es','missing'):
            subject,body=compose(row,locale,'https://example.test')
            self.assertTrue(subject.isascii());self.assertIn('https://example.test/#environments-section',body)
            self.assertNotIn('token=',body);self.assertIn('UTC',body)


class TopicIsolationTests(unittest.TestCase):
    def gateway(self):
        from unittest.mock import Mock
        client=Mock();client.exceptions.NotFoundException=type('NotFoundException',(Exception,),{})
        gateway=SnsEmail(client,'123456789012','ap-southeast-1','cloudhub-test-user-notice-','https://example.test')
        return gateway,client
    def test_owner_and_address_have_distinct_topics_and_confirmation_is_required(self):
        g,c=self.gateway();a='alice@example.test';arn=g.arn('alice',a)
        self.assertNotEqual(arn,g.arn('bob',a));self.assertNotEqual(arn,g.arn('alice','different@example.test'))
        c.create_topic.return_value={'TopicArn':arn};c.list_subscriptions_by_topic.return_value={'Subscriptions':[]}
        self.assertEqual(g.configure('alice',a)['email_status'],'PENDING_CONFIRMATION');c.subscribe.assert_called_once()
        c.list_subscriptions_by_topic.return_value={'Subscriptions':[{'TopicArn':arn,'Endpoint':a,'Protocol':'email','SubscriptionArn':'PendingConfirmation'}]}
        self.assertEqual(g.send('alice',a,{'type':'EXPIRY_SOON'},'en',lambda:True)['email_status'],'PENDING')
        c.publish.assert_not_called()
    def test_foreign_subscriber_fails_closed(self):
        g,c=self.gateway();c.list_subscriptions_by_topic.return_value={'Subscriptions':[{'TopicArn':g.arn('alice','alice@example.test'),
            'Endpoint':'bob@example.test','Protocol':'email','SubscriptionArn':'foreign'}]}
        with self.assertRaises(HubError):g.check('alice','alice@example.test')
        c.publish.assert_not_called()
    def test_stale_before_publish_is_suppressed_and_origin_is_validated(self):
        g,c=self.gateway();arn=g.arn('alice','alice@example.test')
        c.list_subscriptions_by_topic.return_value={'Subscriptions':[{'TopicArn':arn,'Endpoint':'alice@example.test','Protocol':'email','SubscriptionArn':arn+':uuid'}]}
        self.assertEqual(g.send('alice','alice@example.test',{},'en',lambda:False)['email_status'],'SKIPPED_STALE')
        c.publish.assert_not_called()
        with self.assertRaises(ValueError):SnsEmail(c,'123456789012','ap-southeast-1','cloudhub-test-','http://evil.test')


if __name__=='__main__':unittest.main()
