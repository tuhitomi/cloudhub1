"""Production quote/continuous invariants; no AWS calls."""
import sys
import unittest
from copy import deepcopy
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from cloudhub.service import Service
from cloudhub.store import MemoryStore
from cloudhub.cost import Estimator
from cloudhub.errors import HubError
from cloudhub.catalog import configuration_key,configuration_profiles
from cloudhub.worker import Worker
from test_domain import RATES
from test_lifecycle import Processor


class QuoteTests(unittest.TestCase):
    def setUp(self):
        self.now=1000; self.rates=deepcopy(RATES)
        self.s=Service(MemoryStore(), clock=lambda:self.now, estimator=Estimator(self.rates),
            price_provider=lambda:deepcopy(self.rates), verified={'T05'}, budget_milliusd=1000000,
            continuous_enabled=True)
        self.s.regions_config['continuous_verifications']={self.rates['region']:{'T05':{**dict.fromkeys(['passed','old_callback_verified','schedule_transition_verified','source_preservation_verified'],True),'configuration_keys':[configuration_key('T05',None)]}}}
        self.body={'template_id':'T05','estimate_hours':1,'operating_policy':{
            'mode':'AUTO_OFF','period_minutes':60,'ending_policy':'PAUSE',
            'budget_limit_milliusd':None,'confirmed':True}}
        self.driver=Processor(); self.worker=Worker(self.s,self.driver)

    def quoted(self, body=None):
        body=deepcopy(body or self.body)
        quote=self.s.create_estimate('alice',body)
        return {**body,'quote_id':quote['quote_id']}

    def test_continuous_standard_proof_does_not_open_expanded_configuration(self):
        self.assertTrue(self.s.continuous_available({'template_id':'T05','region':self.rates['region']}))
        expanded=next(p['configuration'] for p in configuration_profiles('T05') if p['id']=='expanded')
        self.assertFalse(self.s.continuous_available({'template_id':'T05','region':self.rates['region'],'configuration':expanded}))

    def test_catalog_cached_prices_never_replace_fresh_quote_validation(self):
        calls=[]
        self.s.catalog_price_provider=lambda:(calls.append('bounded_catalog_cache') or deepcopy(self.rates))
        self.s.price_provider=lambda:(calls.append('force_fresh') or deepcopy(self.rates))
        self.s.refresh_pricing(cached=True)
        self.s.create_estimate('alice',self.body)
        self.assertEqual(['bounded_catalog_cache','force_fresh'],calls)

    def test_warm_region_policy_refresh_closes_removed_feature_proof(self):
        row={'template_id':'T05','region':self.rates['region']}
        self.assertTrue(self.s.continuous_available(row))
        self.s.regions_provider=lambda:{'control_region':self.rates['region'],'continuous_verifications':{}}
        self.s.refresh_region_policy()
        self.assertFalse(self.s.continuous_available(row))

    def ready(self, body=None):
        op=self.s.create('alice','create-key-1',self.quoted(body))
        self.finish(op)
        return self.s.store.get('E#'+op['environment_id'])

    def finish(self,op):
        for _ in range(12):
            if self.worker.tick(op['operation_id'])['done']:break

    def reject(self, code, fn):
        with self.assertRaises(HubError) as c:fn()
        self.assertEqual(code,c.exception.code)

    def test_changed_prices_not_silently_accepted(self):
        body=self.quoted();self.rates['units']['ec2_hour']='0.5'
        self.reject('QUOTE_CHANGED',lambda:self.s.create('alice','create-key-1',body))
        self.assertIsNone(self.s.store.get('Q#GLOBAL'))

    def test_continuous_never_accepts_an_unsupported_pause_data_policy(self):
        from cloudhub.operating_policy import validate_policy
        self.reject('PAUSE_UNSUPPORTED',lambda:validate_policy('T07',{**self.body['operating_policy'],'mode':'CONTINUOUS','period_minutes':None,'budget_limit_milliusd':1000}))

    def test_expiry_owner_and_input(self):
        body=self.quoted();self.reject('NOT_FOUND',lambda:self.s.create('bob','create-key-1',body))
        changed={**body,'estimate_hours':2}
        self.reject('QUOTE_CHANGED',lambda:self.s.create('alice','create-key-1',changed))
        self.now+=121;self.reject('QUOTE_EXPIRED',lambda:self.s.create('alice','create-key-1',body))

    def test_duplicate_after_accept_and_expiry_and_changed_body(self):
        body=self.quoted();op=self.s.create('alice','create-key-1',body);self.now+=999
        self.assertEqual(op,self.s.create('alice','create-key-1',body))
        self.reject('IDEMPOTENCY_MISMATCH',lambda:self.s.create('alice','create-key-1',{**body,'estimate_hours':2}))

    def test_two_keys_cannot_consume_one_quote(self):
        body=self.quoted()
        def send(i):
            try:return self.s.create('alice','concurrent-key-'+str(i),body)['operation_id']
            except HubError as e:return e.code
        with ThreadPoolExecutor(max_workers=2) as p:results=list(p.map(send,range(2)))
        self.assertEqual(1,sum(x.startswith('op-') for x in results))
        self.assertIn('QUOTE_CONSUMED',results)
        self.assertEqual(1,self.s.store.get('Q#GLOBAL')['active'])

    def test_renew_quote_change_and_expired_duplicate(self):
        env=self.ready();eid=env['environment_id'];b={'action':'renew','minutes':60}
        q=self.s.management_estimate('alice',eid,b)
        body={'minutes':60,'confirmed':True,'expected_revision':env['lifecycle_revision'],'quote_id':q['quote_id']}
        self.rates['units']['ec2_hour']='0.5'
        self.reject('QUOTE_CHANGED',lambda:self.s.renew('alice',eid,'renew-key-1',body))
        q=self.s.management_estimate('alice',eid,b);body['quote_id']=q['quote_id']
        op=self.s.renew('alice',eid,'renew-key-1',body);self.now+=121
        self.assertEqual(op,self.s.renew('alice',eid,'renew-key-1',body))

    def test_continuous_has_no_deadline_and_old_callbacks_are_harmless(self):
        continuous=deepcopy(self.body);continuous['operating_policy'].update(mode='CONTINUOUS',period_minutes=None)
        env=self.ready(continuous)
        self.assertIsNone(env['deadline']);self.assertNotIn('schedule',self.driver.calls)
        self.now+=99999;self.assertIsNone(self.s.expire(env['environment_id'],expected_deadline=999))
        self.assertEqual('READY',self.s.store.get(env['pk'])['status'])

    def test_mode_change_preserves_resources_and_synchronizes(self):
        env=self.ready();eid=env['environment_id'];ids=deepcopy(env['resources']);old=env['deadline']
        p=deepcopy(self.body['operating_policy']);p.update(mode='CONTINUOUS',period_minutes=None)
        q=self.s.management_estimate('alice',eid,{'action':'change_policy','operating_policy':p})
        op=self.s.change_policy('alice',eid,'change-policy-1',{'operating_policy':p,'expected_revision':1,'quote_id':q['quote_id']})
        self.assertIsNone(self.s.expire(eid,old,1));self.finish(op)
        fresh=self.s.store.get(env['pk']);self.assertIsNone(fresh['deadline']);self.assertEqual(ids,fresh['resources'])
        q=self.s.management_estimate('alice',eid,{'action':'change_policy','operating_policy':self.body['operating_policy']})
        op=self.s.change_policy('alice',eid,'change-policy-2',{'operating_policy':self.body['operating_policy'],'expected_revision':2,'quote_id':q['quote_id']})
        self.finish(op);self.assertEqual(self.now+3600,self.s.store.get(env['pk'])['deadline'])

    def test_continuous_is_not_enabled_implicitly(self):
        self.s.continuous_enabled=False;b=deepcopy(self.body);b['operating_policy'].update(mode='CONTINUOUS',period_minutes=None)
        self.reject('CONTINUOUS_DISABLED',lambda:self.s.create_estimate('alice',b))

    def test_continuous_requires_template_and_region_native_proof_even_with_global_flag(self):
        home=self.rates['region']
        self.assertTrue(self.s.continuous_available({'template_id':'T05','region':home}))
        self.assertFalse(self.s.continuous_available({'template_id':'T05','region':'ap-northeast-1'}))
        self.assertFalse(self.s.continuous_available({'template_id':'T01','region':home}))
        self.s.regions_config['continuous_verifications']={}
        self.assertFalse(self.s.continuous_available({'template_id':'T05','region':home}))

    def test_two_quotes_compete_for_one_budget_reservation(self):
        first=self.quoted();second=self.quoted()
        amount=self.s.store.get('V#'+first['quote_id'])['terms']['estimate']['total_milliusd']
        self.s.budget=amount+1
        def send(pair):
            key,body=pair
            try:return self.s.create('alice',key,body)['operation_id']
            except HubError as error:return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(send,[('budget-key-1',first),('budget-key-2',second)]))
        self.assertEqual(1,sum(x.startswith('op-') for x in results));self.assertIn('BUDGET_EXCEEDED',results)
        self.assertEqual(amount,self.s.store.get('Q#GLOBAL')['reserved_milliusd'])
        self.assertEqual(1,sum(bool(self.s.store.get('V#'+b['quote_id'])['consumed_by']) for b in [first,second]))

    def test_continuous_schedule_failure_keeps_source_and_retry_does_not_recharge(self):
        env=self.ready();eid=env['environment_id'];p={**self.body['operating_policy'],'mode':'CONTINUOUS','period_minutes':None}
        q=self.s.management_estimate('alice',eid,{'action':'change_policy','operating_policy':p})
        op=self.s.change_policy('alice',eid,'policy-error-key',{'operating_policy':p,'expected_revision':1,'quote_id':q['quote_id']})
        before=self.s.store.get('Q#GLOBAL')['reserved_milliusd'];normal=self.driver.cancel_schedule
        def fail(env):raise HubError('SCHEDULE_FAILED','injected cancellation failure',409)
        self.driver.cancel_schedule=fail;self.worker.tick(op['operation_id'])
        fresh=self.s.store.get(env['pk']);self.assertTrue(fresh['schedule_pending']);self.assertIsNone(fresh['deadline']);self.assertEqual('READY',fresh['status'])
        self.driver.cancel_schedule=normal
        retried=self.s.retry_automatic_operation(self.s.store.get(op['pk']));self.finish(retried)
        self.assertFalse(self.s.store.get(env['pk'])['schedule_pending']);self.assertEqual(before,self.s.store.get('Q#GLOBAL')['reserved_milliusd'])

    def test_restore_quote_binds_recovery_retention_and_creates_new_environment(self):
        env=self.ready();eid=env['environment_id']
        quote=self.s.management_estimate('alice',eid,{'action':'backup'})
        op=self.s.command('alice',eid,'backup','backup-test-key',{'quote_id':quote['quote_id']});self.finish(op)
        point=self.s.store.get('R#'+op['recovery_point'])
        request={**self.body,'recovery_point':point['recovery_point']}
        q=self.s.create_estimate('alice',request);request['quote_id']=q['quote_id']
        point['retain_until']-=60;self.s.save(point)
        self.reject('QUOTE_CHANGED',lambda:self.s.create('alice','restore-test-key',request))
        q=self.s.create_estimate('alice',{k:v for k,v in request.items() if k!='quote_id'});request['quote_id']=q['quote_id']
        restored=self.s.create('alice','restore-test-key',request);self.assertNotEqual(eid,restored['environment_id'])
        self.finish(restored);operation=self.s.store.get(restored['pk'])
        self.assertEqual('SUCCEEDED',operation['status']);self.assertIsNotNone(operation['infrastructure_ready_at']);self.assertIsNotNone(operation['data_verified_at'])
