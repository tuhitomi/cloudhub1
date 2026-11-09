"""Local: delayed ECS metadata must not conceal live tasks or read failures."""
import sys,unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from botocore.exceptions import ClientError
from cloudhub.stack_driver import StackDriver
from cloudhub.aws_driver import AWSDriver
from cloudhub.ecs_driver import ECSDriver
from cloudhub.errors import HubError

ARN='arn:aws:ecs:ap-northeast-1:123456789012:task-definition/cloudhub-env-'+('a'*24)+':1'
ITEM={'type':'AWS::ECS::TaskDefinition','id':ARN,'region':'ap-northeast-1'}
ENV={'environment_id':'env-'+'a'*24,'owner_id':'alice','template_id':'T06','resources':[ITEM]}

class ECSRetirementTests(unittest.TestCase):
    def driver(self,status='DELETE_IN_PROGRESS'):
        ecs=Mock();ecs.describe_task_definition.return_value={'taskDefinition':{'taskDefinitionArn':ARN,'status':status}}
        driver=StackDriver({'region':'ap-northeast-1'},{'ecs':ecs})
        driver.inventory=Mock();driver.assert_stack=Mock(return_value=None)
        return driver,ecs
    def test_accepted_async_deletion_does_not_wait_for_metadata_gc(self):
        for status in ['INACTIVE','DELETE_IN_PROGRESS']:
            with self.subTest(status=status):
                driver,ecs=self.driver(status)
                ecs.delete_task_definitions.return_value={'failures':[],'taskDefinitions':[{'taskDefinitionArn':ARN,'status':'DELETE_IN_PROGRESS'}]}
                with patch.object(AWSDriver,'delete',return_value=True):self.assertTrue(driver.delete(deepcopy(ENV),{}))
                self.assertEqual(ecs.delete_task_definitions.call_count,int(status=='INACTIVE'))
    def test_wait_for_stack_and_active_or_unconfirmed_revision(self):
        driver,ecs=self.driver('ACTIVE')
        with patch.object(AWSDriver,'delete',return_value=True):self.assertFalse(driver.delete(deepcopy(ENV),{}))
        ecs.delete_task_definitions.assert_not_called()
        driver,ecs=self.driver('INACTIVE');ecs.delete_task_definitions.return_value={'taskDefinitions':[]}
        with patch.object(AWSDriver,'delete',return_value=True):self.assertFalse(driver.delete(deepcopy(ENV),{}))
        ecs.reset_mock()
        with patch.object(AWSDriver,'delete',return_value=False):self.assertFalse(driver.delete(deepcopy(ENV),{}))
        ecs.describe_task_definition.assert_not_called()
    def test_partial_failure_and_read_failure_are_not_success(self):
        driver,ecs=self.driver('INACTIVE');ecs.delete_task_definitions.return_value={'failures':[{'arn':ARN,'reason':'denied'}]}
        with patch.object(AWSDriver,'delete',return_value=True),self.assertRaises(HubError):driver.delete(deepcopy(ENV),{})
        ecs.describe_task_definition.side_effect=ClientError({'Error':{'Code':'AccessDeniedException','Message':'denied'}},'DescribeTaskDefinition')
        with patch.object(AWSDriver,'delete',return_value=True),self.assertRaises(ClientError):driver.delete(deepcopy(ENV),{})
    def test_pending_revision_is_explicit_and_never_claimed_deleted(self):
        driver,ecs=self.driver();report=driver.audit(deepcopy(ENV),[])
        self.assertEqual(report['pending_deletion'][0]['id'],ARN)
        self.assertFalse(report['pending_deletion'][0]['billable'])
        self.assertEqual(report['pending_deletion'][0]['provider_status'],'DELETE_IN_PROGRESS')
        for key in ['deleted','retained','residual','unknown','billable']:self.assertFalse(report[key])
    def test_metadata_does_not_hide_running_tasks_services_or_stack(self):
        driver,ecs=self.driver();env=deepcopy(ENV)
        task={'type':'ECS::Task','id':'task','cluster':'owned'};service={'type':'AWS::ECS::Service','id':'arn:aws:ecs:ap-northeast-1:123456789012:service/owned/web'}
        env['resources'] += [task,service]
        ecs.describe_tasks.return_value={'tasks':[{'lastStatus':'RUNNING'}]}
        ecs.describe_services.return_value={'services':[{'status':'ACTIVE'}]}
        driver=ECSDriver({'region':'ap-northeast-1'},{'ecs':ecs});driver.assert_stack=Mock(return_value=None);driver.audit_backups=Mock()
        report=driver.audit(env,[])
        self.assertEqual({v['id'] for v in report['residual']},{task['id'],service['id']})
        self.assertEqual({v['id'] for v in report['billable']},{task['id'],service['id']})
        driver.assert_stack.return_value={'StackStatus':'DELETE_IN_PROGRESS'}
        driver._exists=Mock(return_value=True);report=driver.audit(deepcopy(ENV),[])
        self.assertFalse(report['pending_deletion']);self.assertTrue(report['residual'])
    def test_active_inactive_missing_and_denied_are_distinct(self):
        for status in ['ACTIVE','INACTIVE']:
            driver,ecs=self.driver(status);report=driver.audit(deepcopy(ENV),[])
            self.assertTrue(report['residual']);self.assertFalse(report['pending_deletion'])
        driver,ecs=self.driver();ecs.describe_task_definition.side_effect=ClientError({'Error':{'Code':'ClientException','Message':'Unable to describe task definition.'}},'DescribeTaskDefinition')
        self.assertEqual(driver.audit(deepcopy(ENV),[])['deleted'],[ITEM])
        ecs.describe_task_definition.side_effect=ClientError({'Error':{'Code':'AccessDeniedException','Message':'denied'}},'DescribeTaskDefinition')
        report=driver.audit(deepcopy(ENV),[])
        self.assertTrue(report['unknown']);self.assertTrue(report['billable']);self.assertFalse(report['pending_deletion'])

if __name__=='__main__':unittest.main()
