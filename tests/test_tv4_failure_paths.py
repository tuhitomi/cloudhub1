"""Failure callbacks must respect the same ownership/Region boundary as normal ticks."""
from copy import deepcopy
import json,os,sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from botocore.exceptions import ClientError
from cloudhub import runtime
from cloudhub.errors import HubError
import test_lifecycle as fixtures

class FailureBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.LifecycleTests();self.fixture.setUp()
        self.service=self.fixture.service;self.store=self.fixture.store;self.worker=self.fixture.worker
        self.env=self.fixture.ready(self.fixture.policy(ending='BACKUP_RETIRE'))

    def backup(self):
        return self.service.command('alice',self.env['environment_id'],'backup','fault-boundary-backup',{})

    def test_failure_callback_cannot_mutate_another_owners_environment(self):
        op=self.backup();op=self.store.get('O#'+op['operation_id']);op['owner_id']='bob';self.service.save(op)
        before=deepcopy(self.store.rows);calls=list(self.fixture.driver.calls)
        with self.assertRaises(HubError):self.worker.fail(op['operation_id'],'synthetic failure')
        self.assertEqual(before,self.store.rows);self.assertEqual(calls,self.fixture.driver.calls)

    def test_failure_callback_cannot_cross_the_operations_region(self):
        op=self.backup();op=self.store.get('O#'+op['operation_id']);op['region']='us-east-1';self.service.save(op)
        before=deepcopy(self.store.rows)
        with self.assertRaises(HubError):self.worker.fail(op['operation_id'],'synthetic failure')
        self.assertEqual(before,self.store.rows)

    def test_failure_callback_cannot_mark_a_foreign_recovery_point_failed(self):
        op=self.backup();row=self.store.get('O#'+op['operation_id']);rp=self.store.get('R#'+row['recovery_point'])
        rp['owner_id']='bob';self.service.save(rp);before=deepcopy(self.store.rows)
        with self.assertRaises(HubError):self.worker.fail(op['operation_id'],'synthetic failure')
        self.assertEqual(before,self.store.rows)

    def test_old_generation_failure_is_a_noop_before_any_mutation(self):
        op=self.backup();before=deepcopy(self.store.rows)
        self.assertTrue(self.worker.fail(op['operation_id'],'old callback',generation=999)['done'])
        self.assertEqual(before,self.store.rows)

    def test_dispatch_failure_leaves_one_durable_operation_for_the_outbox(self):
        self.fixture.now=self.env['deadline'];event={'environment_id':self.env['environment_id'],
            'expected_deadline':self.env['deadline'],'expected_revision':self.env['lifecycle_revision']}
        before=len([r for r in self.store.rows.values() if r.get('kind')=='operation'])
        with patch.object(runtime,'build_service',return_value=self.service),patch.object(runtime,'dispatch',side_effect=TimeoutError('synthetic')):
            with self.assertRaises(TimeoutError):runtime.expiry_handler(event)
            self.assertFalse(runtime.expiry_handler(event)['accepted'])
        queued=[r for r in self.store.rows.values() if r.get('kind')=='operation' and r.get('status')=='QUEUED']
        self.assertEqual(len(queued),1);self.assertEqual(len([r for r in self.store.rows.values() if r.get('kind')=='operation']),before+1)
        current=self.store.get(self.env['pk']);self.assertEqual(current['lock'],queued[0]['operation_id'])
        self.assertNotIn('delete',self.fixture.driver.calls)

    def test_duplicate_dispatch_uses_the_same_execution_identity_and_keeps_quota(self):
        op=self.backup();client=Mock();client.start_execution.side_effect=ClientError({'Error':{'Code':'ExecutionAlreadyExists'}},'StartExecution')
        quota=deepcopy(self.store.get('Q#GLOBAL'))
        with patch.object(runtime,'build_service',return_value=self.service),patch('boto3.client',return_value=client),\
             patch.dict(os.environ,{'STATE_MACHINE_ARN':'arn:aws:states:us-east-1:123456789012:stateMachine:local'}):
            runtime.dispatch(op['operation_id']);runtime.dispatch(op['operation_id'])
        calls=client.start_execution.call_args_list;self.assertEqual(calls[0],calls[1])
        self.assertEqual(calls[0].kwargs['name'],op['operation_id']);self.assertEqual(quota,self.store.get('Q#GLOBAL'))
        self.assertEqual(json.loads(calls[0].kwargs['input'])['operation_id'],op['operation_id'])

if __name__=='__main__':unittest.main()
