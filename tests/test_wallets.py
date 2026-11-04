"""Wallet isolation and atomic admission; local only, no live AWS charges."""
import sys,unittest
import json,os
from unittest.mock import patch
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from cloudhub.service import Service,expected
from cloudhub.store import MemoryStore
from cloudhub.registration import ensure_profile,defaults,set_defaults
from cloudhub.wallet import budget_refusal
from cloudhub.cost import Estimator
from cloudhub.errors import HubError
from cloudhub import api
from test_domain import RATES

def identity(owner):return {'owner_id':owner,'email':owner+'@example.com','email_verified':True}

class WalletTests(unittest.TestCase):
    def setUp(self):
        self.s=Service(MemoryStore(),clock=lambda:1000,budget_milliusd=133200,estimator=Estimator(RATES),verified={'T01'},require_quotes=False)
        ensure_profile(self.s,identity('alice'));ensure_profile(self.s,identity('bob'))
    def test_each_new_account_gets_ten_independent_credits_once(self):
        self.assertEqual(defaults(self.s)['budget_milliusd'],10000)
        with ThreadPoolExecutor(max_workers=8) as pool:list(pool.map(lambda _:ensure_profile(self.s,identity('alice')),range(16)))
        a=self.s.limits('alice');b=self.s.limits('bob')
        self.assertEqual((a['wallet']['granted_milliusd'],b['wallet']['balance_milliusd']),(10000,10000))
        self.assertFalse(a['wallet']['is_money']);self.assertFalse(a['wallet']['is_aws_credit'])
        self.assertIsNone(self.s.store.get('Q#GLOBAL'))
    def test_other_users_do_not_debit_wallet_and_legacy_admission_stays_safe(self):
        row=self.s.store.get('Q#GLOBAL') or {'pk':'Q#GLOBAL','active':0,'reserved_milliusd':133077}
        self.s.store.commit([row],expected(row))
        value=self.s.limits('alice')
        self.assertEqual(value['wallet']['balance_milliusd'],10000)
        self.assertEqual(value['user_remaining_milliusd'],10000)
        self.assertEqual(value['remaining_milliusd'],123)
        self.assertEqual(value['platform_budget']['remaining_milliusd'],123)
        before=deepcopy(self.s.store.rows)
        with self.assertRaises(HubError) as error:self.s.create('alice','wallet-platform-create',{'template_id':'T01','duration_hours':1})
        self.assertEqual(error.exception.details['budget_scope'],'PLATFORM')
        self.assertEqual(self.s.store.rows,before)
    def test_wallet_refusal_is_separate_from_platform_and_keeps_source_rows(self):
        self.s.set_limits('admin','alice',{'max_active':2,'budget_milliusd':0})
        with self.assertRaises(HubError) as error:self.s.create('alice','wallet-personal-create',{'template_id':'T01','duration_hours':1})
        self.assertEqual(error.exception.code,'BUDGET_EXCEEDED');self.assertEqual(error.exception.details['budget_scope'],'ACCOUNT_WALLET')
        self.assertEqual(self.s.limits('bob')['wallet']['balance_milliusd'],10000)
    def test_success_and_idempotent_retry_charge_only_the_owner_once(self):
        body={'template_id':'T01','duration_hours':1};op=self.s.create('alice','wallet-accepted-key',body)
        first=self.s.limits('alice')['wallet'];self.s.create('alice','wallet-accepted-key',body)
        self.assertEqual(first,self.s.limits('alice')['wallet'])
        self.assertGreater(first['committed_milliusd'],0)
        self.assertEqual(self.s.limits('bob')['wallet']['balance_milliusd'],10000)
        self.assertEqual(self.s.store.get('Q#GLOBAL')['reserved_milliusd'],first['committed_milliusd'])
    def test_parallel_spend_cannot_overdraw_one_wallet_or_shared_cap(self):
        amount=self.s.validate_create({'template_id':'T01','duration_hours':1})[2]['total_milliusd']
        self.s.set_limits('admin','alice',{'max_active':4,'budget_milliusd':amount})
        def create(i):
            try:return self.s.create('alice','wallet-parallel-'+str(i),{'template_id':'T01','duration_hours':1})
            except HubError:return None
        with ThreadPoolExecutor(max_workers=8) as pool:results=list(pool.map(create,range(12)))
        self.assertEqual(sum(r is not None for r in results),1)
        self.assertEqual(self.s.limits('alice')['wallet']['balance_milliusd'],0)
        self.assertEqual(len(self.s.store.scan_kind('operation')),1)
    def test_existing_credit_and_ledger_are_preserved_when_signup_default_changes(self):
        q=self.s.store.get('Q#alice');q.update(budget_milliusd=120000,reserved_milliusd=5000);self.s.store.commit([q],expected(q))
        before=deepcopy(self.s.store.get('Q#alice'));set_defaults(self.s,'admin',{'max_active':2,'budget_milliusd':10000})
        ensure_profile(self.s,identity('alice'))
        self.assertEqual(self.s.store.get('Q#alice'),before)
        self.assertEqual(self.s.limits('alice')['wallet']['balance_milliusd'],115000)
    def test_admin_changes_total_allocation_without_refunding_history(self):
        self.s.create('alice','wallet-before-adjust',{'template_id':'T01','duration_hours':1})
        used=self.s.limits('alice')['wallet']['committed_milliusd']
        self.s.set_limits('admin','alice',{'max_active':2,'budget_milliusd':20000})
        wallet=self.s.limits('alice')['wallet'];self.assertEqual(wallet['balance_milliusd'],20000-used)
        self.assertEqual(wallet['committed_milliusd'],used)
        self.assertEqual(self.s.store.list_owner('alice','wallet_adjustment')[0]['granted_milliusd'],20000)
    def test_unknown_legacy_amount_stays_debited_and_missing_cap_is_not_reset(self):
        q=self.s.store.get('Q#alice');q.pop('budget_milliusd');q.update(reserved_milliusd=4000);self.s.store.commit([q],expected(q))
        wallet=self.s.limits('alice')['wallet'];self.assertEqual(wallet['granted_milliusd'],133200)
        self.assertEqual(wallet['legacy_unreconciled_milliusd'],4000)
        self.assertEqual(wallet['balance_milliusd'],129200)
    def test_authenticated_wallet_ignores_other_owner_query_and_cannot_self_credit(self):
        self.s.set_limits('admin','bob',{'max_active':2,'budget_milliusd':20000})
        event={'rawPath':'/limits','queryStringParameters':{'owner_id':'bob'},'requestContext':{'http':{'method':'GET'},
            'authorizer':{'jwt':{'claims':{'sub':'alice','username':'alice','token_use':'access'}}}}}
        with patch.object(api,'SERVICE',self.s),patch.object(api,'DISPATCH',None),patch.dict(os.environ,{'USER_POOL_ID':'local'}),patch('cloudhub.accounts.Accounts',autospec=True) as accounts:
            accounts.return_value.identity.return_value=identity('alice')
            response=api.handler(event);self.assertEqual(response['statusCode'],200)
            self.assertEqual(json.loads(response['body'])['wallet']['granted_milliusd'],10000)
            event.update(rawPath='/admin/users/alice/limits',body=json.dumps({'max_active':2,'budget_milliusd':20000}))
            event['requestContext']['http']['method']='POST'
            self.assertEqual(api.handler(event)['statusCode'],403)
        self.assertEqual(self.s.limits('alice')['wallet']['granted_milliusd'],10000)

if __name__=='__main__':unittest.main()
