"""Local legacy record replay, not native in-flight workflow acceptance."""
from copy import deepcopy
from unittest import TestCase
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import test_quotes_continuous as fixtures
from cloudhub.worker import Worker
from migrate_forecast_ledger import prepare,apply_plan

class CompatibilityTests(TestCase):
    def test_pre_quote_operation_keeps_identity_generation_and_reservation(self):
        f=fixtures.QuoteTests();f.setUp();f.s.require_quotes=False
        oldbody={'template_id':'T05','duration_hours':1}
        op=f.s.create('alice','legacy-create-key',oldbody);eid=op['environment_id']
        # Represent the old record contract, which had no F# or quote records.
        f.s.store.rows.pop('F#'+op['operation_id'])
        for key in ['Q#GLOBAL','Q#alice']:
            old=f.s.store.rows[key]
            f.s.store.rows[key]={k:old[k] for k in ['pk','active','reserved_milliusd','version']}
        env=f.s.store.rows['E#'+eid]
        for k in ['operating_schema','operating_policy','open_forecast_reservations','first_period_estimate']:env.pop(k,None)
        f.s.store.rows[op['pk']]['generation']=2
        before=deepcopy(f.s.store.get('Q#GLOBAL'));f.s.require_quotes=True;f.now+=121
        replay=f.s.create('alice','legacy-create-key',oldbody)
        self.assertEqual(op['operation_id'],replay['operation_id']);self.assertEqual(2,replay['generation'])
        worker=Worker(f.s,f.driver)
        for _ in range(12):
            if worker.tick(op['operation_id'],2)['done']:break
        self.assertEqual('SUCCEEDED',f.s.store.get(op['pk'])['status'])
        self.assertEqual(before,f.s.store.get('Q#GLOBAL'))
        self.assertIsNone(f.s.store.get('F#'+op['operation_id']))
        self.assertEqual(1,f.driver.calls.count('create'))

    def test_full_legacy_snapshot_keeps_unrecognised_fields_and_replay_is_safe(self):
        from cloudhub.store import MemoryStore
        store=MemoryStore();row={'pk':'Q#alice','active':0,'reserved_milliusd':700,
            'max_active':2,'budget_milliusd':900,'operator_annotation':'retain audit context'}
        store.commit([row],{row['pk']:None});source=store.get(row['pk']);plan=prepare([source],1234)
        apply_plan(store,plan);after=store.get(row['pk']);apply_plan(store,plan)
        self.assertEqual(after,store.get(row['pk']));self.assertEqual(700,after['legacy_unallocated_milliusd'])
        self.assertEqual(700,after['reserved_milliusd']);self.assertEqual(900,after['budget_milliusd'])
        self.assertEqual(source['operator_annotation'],after['operator_annotation'])
