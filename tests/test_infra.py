import json
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from cloudhub.templates import linux_template
from cloudhub.catalog import catalog

class InfraTests(unittest.TestCase):
    def test_snapshot_deletion_is_only_for_own_regional_tagged_cloudhub_backups(self):
        sys.path.insert(0,str(ROOT/'scripts'))
        from generate_infra import build_template
        resources=build_template()['Resources']
        for name in ['WorkerFunction','SweepFunction','ApiFunction','ExpiryFunction']:
            policies=resources[name]['Properties']['Policies']
            statements=[s for p in policies if isinstance(p,dict) for s in p.get('Statement',[])]
            selected=[s for s in statements if s.get('Action')=='ec2:DeleteSnapshot']
            self.assertEqual(len(selected),1 if name in {'WorkerFunction','SweepFunction'} else 0)
            if selected:
                s=selected[0]
                self.assertEqual(s['Resource'],{'Fn::Sub':'arn:${AWS::Partition}:ec2:${AWS::Region}::snapshot/snap-*'})
                self.assertEqual(s['Condition']['StringEquals'],{'aws:RequestedRegion':{'Ref':'AWS::Region'},'ec2:Owner':{'Ref':'AWS::AccountId'}})
                self.assertEqual(s['Condition']['StringLike'],{'ec2:ResourceTag/cloudhub:environment':'env-*','ec2:ResourceTag/cloudhub:recovery':'rp-*'})
                self.assertEqual(s['Condition']['Null'],{'ec2:ResourceTag/cloudhub:owner':'false'})

    def test_catalog_order_and_gate(self):
        entries=catalog([])
        self.assertEqual([t['template_id'] for t in entries],['T%02d'%i for i in range(1,10)])
        self.assertTrue(all(not t['create_enabled'] for t in entries))
    def test_restore_never_formats_and_has_no_shared_resources(self):
        env={'environment_id':'env-test','owner_id':'alice','template_id':'T01'}
        settings={'availability_zone':'us-east-1a','ami_id':'ami-0123456789abcdef0','vpc_id':'vpc-0123456789abcdef0','public_subnet_id':'subnet-0123456789abcdef0','instance_profile':'shared-ssm','ssh_cidr':'192.0.2.1/32'}
        template=linux_template(env,settings,'snap-0123456789abcdef0')
        self.assertEqual(template['Resources']['DataVolume']['Properties']['SnapshotId'],'snap-0123456789abcdef0')
        script,variables=template['Resources']['Instance']['Properties']['UserData']['Fn::Base64']['Fn::Sub']
        self.assertNotIn('mkfs',variables['FormatCommand'])
        self.assertEqual(template['Resources']['Instance']['Properties']['MetadataOptions']['HttpTokens'],'required')
        self.assertTrue(template['Resources']['Instance']['Properties']['PropagateTagsToVolumeOnCreation'])
        self.assertNotIn('AWS::EC2::VPC',[r['Type'] for r in template['Resources'].values()])
        self.assertEqual(template['Resources']['SecurityGroup']['Properties']['SecurityGroupIngress'][0]['CidrIp'],'192.0.2.1/32')
    def test_workflow_wait_and_failure_handler(self):
        workflow=json.loads((ROOT/'infra/lifecycle.asl.json').read_text())
        self.assertEqual(workflow['States']['Wait']['Type'],'Wait')
        self.assertLessEqual(workflow['States']['Tick']['Retry'][0]['MaxAttempts'],3)
        self.assertEqual(workflow['States']['Tick']['Catch'][0]['Next'],'MarkFailure')
        self.assertEqual(workflow['States']['CheckFailure']['Choices'][0]['Next'],'Failed')
    def test_control_plane_protected_data_and_scheduler_fallback(self):
        cf=json.loads((ROOT/'infra/control-plane.json').read_text())
        r=cf['Resources']
        self.assertEqual(r['Table']['DeletionPolicy'],'Retain')
        self.assertEqual(r['BackupVault']['DeletionPolicy'],'Retain')
        self.assertEqual(r['FallbackScan']['Properties']['ScheduleExpression'],'rate(5 minutes)')
        auth=r['HttpApi']['Properties']['Auth']['Authorizers']['CognitoJwt']
        self.assertIn('cloudhub/use',auth['AuthorizationScopes'])

if __name__=='__main__':unittest.main()
