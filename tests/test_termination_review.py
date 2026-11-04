"""Cost-reducing commands remain available without a price provider/reservation."""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
import test_quotes_continuous as fixtures
from unittest import TestCase
from cloudhub.errors import HubError


class TerminationTests(TestCase):
    setUp=fixtures.QuoteTests.setUp
    ready=fixtures.QuoteTests.ready
    quoted=fixtures.QuoteTests.quoted
    finish=fixtures.QuoteTests.finish
    reject=fixtures.QuoteTests.reject
    def review(self,env,action='end'):
        q=self.s.management_estimate('alice',env['environment_id'],{'action':action})
        return {'quote_id':q['quote_id'],'expected_revision':env['lifecycle_revision'],'confirmed':True}

    def test_failed_mandatory_retirement_backup_can_retry_without_prices_or_new_reservation(self):
        env=self.ready();eid=env['environment_id'];op=self.s.command('alice',eid,'destroy','retire-before-retry',self.review(env,'destroy'))
        self.driver.fail_backup=True;self.worker.tick(op['operation_id']);self.assertNotIn('delete',self.driver.calls)
        before=deepcopy(self.s.store.get('Q#GLOBAL'));self.s.budget=before['reserved_milliusd'];self.s.price_provider=Mock(side_effect=RuntimeError('offline'))
        self.s.estimator.estimate=Mock(side_effect=RuntimeError('missing prices'))
        self.reject('NOT_FOUND',lambda:self.s.control_operation('bob',op['operation_id'],'retry','cross-retry-01',{}))
        retried=self.s.control_operation('alice',op['operation_id'],'retry','retire-retry-01',{})
        self.assertEqual(retried['phase'],'BACKUP');self.assertNotEqual(retried['recovery_point'],op['recovery_point']);self.assertEqual(before,self.s.store.get('Q#GLOBAL'))
        self.assertEqual(retried,self.s.control_operation('alice',op['operation_id'],'retry','retire-retry-01',{}))
        self.assertTrue(any(x['reason']=='UNPRICED_MANDATORY_RETENTION_RETRY' and x['amount_milliusd'] is None for x in self.s.store.list_owner('alice','ledger_exposure')))
        self.s.price_provider.assert_not_called();self.s.estimator.estimate.assert_not_called()

    def test_pause_works_at_full_budget_with_broken_provider(self):
        env=self.ready();self.s.budget=self.s.store.get('Q#GLOBAL')['reserved_milliusd']
        self.s.price_provider=Mock(side_effect=RuntimeError('SSM unavailable'))
        b=self.review(env);op=self.s.end('alice',env['environment_id'],'end-key-1',b)
        self.assertEqual('PAUSE',op['phase']);self.s.price_provider.assert_not_called()

    def test_retirement_with_unpriced_retention_preserves_accounting_and_backup(self):
        env=self.ready();old=deepcopy(self.s.store.get('Q#GLOBAL'));self.s.price_provider=Mock(side_effect=RuntimeError('SSM unavailable'))
        self.s.budget=old['reserved_milliusd'];b=self.review(env,'destroy')
        op=self.s.command('alice',env['environment_id'],'destroy','destroy-key-1',b)
        self.assertEqual('BACKUP',op['phase']);self.assertIsNotNone(op['recovery_point'])
        self.assertEqual(old,self.s.store.get('Q#GLOBAL'))
        self.assertTrue(self.s.store.get(env['pk'])['retirement_cost_reconciliation_required'])
        self.assertEqual(1,len(self.s.store.list_owner('alice','ledger_exposure')))
        self.now+=999;self.assertEqual(op,self.s.command('alice',env['environment_id'],'destroy','destroy-key-1',b))
        self.s.price_provider.assert_not_called()

    def test_termination_review_owner_expiry_consumed_revision_and_concurrency(self):
        env=self.ready();eid=env['environment_id'];b=self.review(env)
        self.reject('NOT_FOUND',lambda:self.s.end('bob',eid,'end-key-1',b))
        self.now+=121;self.reject('QUOTE_EXPIRED',lambda:self.s.end('alice',eid,'end-key-1',b))
        b=self.review(env);self.reject('STALE_REVISION',lambda:self.s.end('alice',eid,'end-key-1',{**b,'expected_revision':99}))
        def send(i):
            try:return self.s.end('alice',eid,'parallel-end-'+str(i),b)['operation_id']
            except HubError as exc:return exc.code
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(send,range(2)))
        self.assertEqual(1,sum(x.startswith('op-') for x in rows))

    def test_price_failures_and_unapproved_rates_do_not_gate_ending(self):
        env=self.ready()
        for mutate in [lambda:self.rates.update(approved=False),lambda:self.rates['units'].clear()]:
            mutate()
            self.assertTrue(self.review(env)['confirmed'])

    def test_explicit_backup_still_needs_price_and_budget_but_retire_never_deletes_on_backup_failure(self):
        env=self.ready();eid=env['environment_id'];q=self.s.management_estimate('alice',eid,{'action':'backup'})
        self.s.budget=self.s.store.get('Q#GLOBAL')['reserved_milliusd']
        self.reject('BUDGET_EXCEEDED',lambda:self.s.command('alice',eid,'backup','backup-limit-key',{'quote_id':q['quote_id']}))
        b=self.review(env,'destroy');op=self.s.command('alice',eid,'destroy','destroy-fail-key',b)
        self.driver.fail_backup=True;self.worker.tick(op['operation_id'])
        self.assertNotIn('delete',self.driver.calls)
        self.assertEqual('ERROR_RETAINED',self.s.store.get(env['pk'])['status'])
        self.assertTrue(self.s.store.get(env['pk'])['resources'])

    def test_consumed_consent_cannot_be_reused_and_accepted_legacy_retry_is_preserved(self):
        env=self.ready();eid=env['environment_id'];b=self.review(env);op=self.s.end('alice',eid,'first-end-key',b)
        row=self.s.store.get('V#'+b['quote_id']);self.assertEqual(op['operation_id'],row['consumed_by'])
        self.reject('QUOTE_CONSUMED',lambda:self.s.consume_termination('alice',env,'end',b,'op-other'))
        self.s.require_quotes=False
        oldbody={'confirmed':True};self.s.finish(op,self.s.store.get(env['pk']))
        current=self.s.store.get(env['pk']);current.update(status='READY',lock=None);self.s.save(current)
        legacy=self.s.end('alice',eid,'legacy-end-key',oldbody)
        self.s.require_quotes=True;self.now+=999
        self.assertEqual(legacy,self.s.end('alice',eid,'legacy-end-key',oldbody))
