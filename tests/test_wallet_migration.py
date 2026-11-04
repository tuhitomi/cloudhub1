import sys,unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'));sys.path.insert(0,str(ROOT/'scripts'))
from cloudhub.store import MemoryStore
from cloudhub.service import expected
from cloudhub.errors import Conflict
from migrate_account_wallets import plan,pin

class WalletMigrationTests(unittest.TestCase):
    def test_preview_excludes_global_and_explicit_caps_and_changes_nothing(self):
        rows=[{'pk':'Q#GLOBAL'},{'pk':'Q#old','reserved_milliusd':2300},{'pk':'Q#explicit','budget_milliusd':9000},{'pk':'E#env'}]
        before=deepcopy(rows);preview=plan(rows,133200)
        self.assertEqual(len(preview['items']),1);self.assertEqual(preview['items'][0]['pk'],'Q#old');self.assertEqual(rows,before)
    def test_apply_preserves_history_and_is_repeatable_without_refunds(self):
        store=MemoryStore();row={'pk':'Q#old','active':1,'reserved_milliusd':4000,'future_reserved_milliusd':1000,'accrued_estimate_milliusd':2000,'legacy_unallocated_milliusd':1000}
        store.commit([row],expected(row));item=plan([row],133200)['items'][0]
        self.assertEqual(pin(store,item,1000),'PINNED');after=store.get(row['pk'])
        self.assertTrue(all(after[k]==v for k,v in row.items()));self.assertEqual(after['budget_milliusd'],133200)
        self.assertEqual(pin(store,item,1001),'ALREADY_EXPLICIT');self.assertEqual(after,store.get(row['pk']))
        self.assertEqual(len(store.scan_kind('wallet_migration')),1)
    def test_concurrent_admin_credit_update_wins_and_is_never_overwritten(self):
        store=MemoryStore();row={'pk':'Q#old','active':0,'reserved_milliusd':1000};store.commit([row],expected(row));item=plan([row],133200)['items'][0]
        row=store.get(row['pk']);row['budget_milliusd']=20000;store.commit([row],expected(row))
        self.assertEqual(pin(store,item,1000),'ALREADY_EXPLICIT');self.assertEqual(store.get(row['pk'])['budget_milliusd'],20000)
    def test_retry_preserves_new_accounting_state(self):
        store=MemoryStore();row={'pk':'Q#old','active':0,'reserved_milliusd':1000};store.commit([row],expected(row));item=plan([row],133200)['items'][0];original=store.commit;calls=0
        def race(rows,versions):
            nonlocal calls
            calls+=1
            if calls==1:
                current=store.get('Q#old');current['reserved_milliusd']=1200;original([current],expected(current));raise Conflict()
            return original(rows,versions)
        with patch.object(store,'commit',side_effect=race):self.assertEqual(pin(store,item,1000),'PINNED')
        self.assertEqual(store.get('Q#old')['reserved_milliusd'],1200)
    def test_missing_rows_require_review_and_no_global_or_explicit_record_is_planned(self):
        with self.assertRaises(ValueError):plan([],None)
        for pk in ['Q#GLOBAL','Q#','E#other']:
            with self.assertRaises(ValueError):pin(MemoryStore(),{'pk':pk,'pin_milliusd':133200},1000)
        self.assertEqual(pin(MemoryStore(),{'pk':'Q#missing','pin_milliusd':133200},1000),'MISSING_REVIEW_REQUIRED')
