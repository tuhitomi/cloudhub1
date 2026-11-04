"""Forecast classifications and release invariants; no AWS billing claims."""
import test_quotes_continuous as fixtures
import unittest
from cloudhub.ledger import normalize


class LedgerTests(unittest.TestCase):
    setUp=fixtures.QuoteTests.setUp
    quoted=fixtures.QuoteTests.quoted
    ready=fixtures.QuoteTests.ready
    finish=fixtures.QuoteTests.finish
    def test_legacy_migration_does_not_refund_unidentified_cost(self):
        row={'pk':'Q#GLOBAL','reserved_milliusd':114575,'active':0}
        normalize(row,1000);normalize(row,2000)
        self.assertEqual(114575,row['legacy_unallocated_milliusd'])
        self.assertEqual(114575,row['reserved_milliusd'])
        self.assertEqual(0,row['future_reserved_milliusd'])

    def test_elapsed_forecast_and_unused_release_are_not_refunded_history(self):
        env=self.ready();before=self.s.store.get('Q#GLOBAL');self.now+=900
        self.s.settle_ledger(env['environment_id']);middle=self.s.store.get('Q#GLOBAL')
        self.assertGreater(middle['accrued_estimate_milliusd'],0)
        self.assertEqual(before['reserved_milliusd'],middle['reserved_milliusd'])
        env=self.s.store.get(env['pk']);env.update(status='PAUSED',paused_at=self.now);self.s.save(env)
        self.s.settle_ledger(env['environment_id']);after=self.s.store.get('Q#GLOBAL')
        self.assertGreater(after['released_estimate_milliusd'],0)
        self.assertEqual(middle['accrued_estimate_milliusd'],after['accrued_estimate_milliusd'])
        self.s.settle_ledger(env['environment_id']);self.assertEqual(after['reserved_milliusd'],self.s.store.get('Q#GLOBAL')['reserved_milliusd'])

    def test_failed_creation_reservation_requires_reconciliation(self):
        op=self.s.create('alice','create-key-1',self.quoted());env=self.s.store.get('E#'+op['environment_id'])
        env.update(status='DELETED',retired_at=self.now);self.s.save(env);self.s.settle_ledger(env['environment_id'])
        r=self.s.store.get('F#'+op['operation_id'])
        self.assertEqual('RECONCILIATION_REQUIRED',r['status']);self.assertEqual(0,r['released_milliusd'])

    def test_continuous_threshold_warns_and_preserves_source(self):
        body=self.body.copy();body['operating_policy']={**self.body['operating_policy'],'mode':'CONTINUOUS','period_minutes':None,'budget_limit_milliusd':1}
        env=self.ready(body);self.now+=7200;self.s.continuous_observation(env['environment_id'])
        self.assertEqual('READY',self.s.store.get(env['pk'])['status'])
        self.assertEqual(1,len(self.s.store.list_owner('alice','notification')))
        self.s.continuous_observation(env['environment_id']);self.assertEqual(1,len(self.s.store.list_owner('alice','notification')))

    def test_continuous_advisory_outbox_retries_emission_without_deleting_source(self):
        body=self.body.copy();body['operating_policy']={**self.body['operating_policy'],'mode':'CONTINUOUS','period_minutes':None,'budget_limit_milliusd':1}
        env=self.ready(body);self.s.continuous_observation(env['environment_id'])
        def unavailable(_):raise OSError('log unavailable')
        with self.assertRaises(OSError):self.s.emit_continuous_notices(env['environment_id'],unavailable)
        note=self.s.store.list_owner('alice','notification')[0]
        self.assertNotIn('operational_log_emitted_at',note)
        events=[];self.s.emit_continuous_notices(env['environment_id'],events.append)
        self.s.emit_continuous_notices(env['environment_id'],events.append)
        self.assertEqual(1,len(events));self.assertEqual('alice',events[0]['owner_id'])
        self.assertEqual('ALERT_ONLY_PRESERVE_SOURCE',events[0]['action'])
        self.assertEqual('READY',self.s.store.get(env['pk'])['status'])

    def test_migration_preview_apply_and_retry_keep_history_and_amounts(self):
        from migrate_forecast_ledger import prepare,apply_plan
        old={'pk':'Q#alice','active':0,'reserved_milliusd':900,'budget_milliusd':5000}
        self.s.store.commit([old],{'Q#alice':None});old=self.s.store.get('Q#alice')
        plan=prepare([old],self.now);self.assertEqual(0,plan['refunds'])
        apply_plan(self.s.store,plan);apply_plan(self.s.store,plan)
        row=self.s.store.get('Q#alice');self.assertEqual(900,row['legacy_unallocated_milliusd']);self.assertEqual(900,row['reserved_milliusd']);self.assertEqual(5000,row['budget_milliusd'])
        self.assertEqual(1,len(self.s.store.scan_kind('ledger_migration')))

    def test_pause_release_is_frozen_after_a_later_resume(self):
        env=self.ready();self.now+=600
        env=self.s.store.get(env['pk']);env.update(status='PAUSED',paused_at=self.now);self.s.save(env)
        self.s.settle_ledger(env['environment_id']);before=self.s.store.get('Q#GLOBAL')
        env=self.s.store.get(env['pk']);env.update(status='READY',ready_at=self.now+1);self.s.save(env);self.now+=7200
        self.s.settle_ledger(env['environment_id']);after=self.s.store.get('Q#GLOBAL')
        self.assertEqual(before['released_estimate_milliusd'],after['released_estimate_milliusd'])
        self.assertEqual(before['accrued_estimate_milliusd'],after['accrued_estimate_milliusd'])

    def test_continuous_observation_accumulates_across_pause_and_resume(self):
        body={**self.body,'operating_policy':{**self.body['operating_policy'],'mode':'CONTINUOUS','period_minutes':None}}
        env=self.ready(body);eid=env['environment_id'];self.now+=86400
        self.s.continuous_observation(eid);first=self.s.store.get(env['pk'])['continuous_unreserved_observed_milliusd'];self.assertGreater(first,0)
        q=self.s.management_estimate('alice',eid,{'action':'end'})
        op=self.s.end('alice',eid,'continuous-pause',{'confirmed':True,'expected_revision':env['lifecycle_revision'],'quote_id':q['quote_id']});self.finish(op)
        q=self.s.management_estimate('alice',eid,{'action':'resume_paused'})
        op=self.s.resume_paused('alice',eid,'continuous-resume',{'confirmed':True,'quote_id':q['quote_id']});self.finish(op)
        self.now+=86400;self.s.continuous_observation(eid)
        second=self.s.store.get(env['pk'])['continuous_unreserved_observed_milliusd'];self.assertGreater(second,first)
        self.s.continuous_observation(eid);self.assertEqual(second,self.s.store.get(env['pk'])['continuous_unreserved_observed_milliusd'])

    def test_missing_continuous_prices_stay_unknown_and_raise_a_notice(self):
        body={**self.body,'operating_policy':{**self.body['operating_policy'],'mode':'CONTINUOUS','period_minutes':None}}
        env=self.ready(body);self.rates['approved']=False;self.s.refresh_pricing();self.s.continuous_observation(env['environment_id'])
        fresh=self.s.store.get(env['pk']);self.assertIsNone(fresh['continuous_cost_observation']['estimated_milliusd']);self.assertEqual('READY',fresh['status'])
        self.assertTrue(any(n['type']=='CONTINUOUS_COST_UNAVAILABLE' for n in self.s.store.list_owner('alice','notification')))
