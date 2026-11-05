"""Local security/scope checks for regional deployment documents; not AWS proof."""
import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from regional_runtime import prepare
from generate_infra import build_template

HOME='ap-southeast-1';TARGET='ap-northeast-1';ACCOUNT='123456789012'

def sample(region=TARGET):
    home={'account_id':ACCOUNT,'backup_role':'arn:aws:iam::'+ACCOUNT+':role/backup',
        'backup_restore_role':'arn:aws:iam::'+ACCOUNT+':role/restore','management_table_arn':'arn:aws:dynamodb:'+HOME+':'+ACCOUNT+':table/control',
        'management_table':'control','instance_profile':'session','ssh_cidr':'192.0.2.1/32','postgres_version':'16.15'}
    identities={'SessionRole':{'name':'session','arn':'arn:aws:iam::'+ACCOUNT+':role/session'},'SessionProfile':'session'}
    return prepare(build_template(),home,identities,region,'ami-0123456789abcdef0')

class RegionalRuntimeTests(unittest.TestCase):
    def test_runtime_has_no_workload_compute_and_private_database_routes_have_no_internet(self):
        r=sample()['template']['Resources']
        self.assertFalse(any(v['Type'] in {'AWS::EC2::Instance','AWS::RDS::DBInstance','AWS::EC2::NatGateway','AWS::Lambda::Function'} for v in r.values()))
        self.assertEqual(r['Db1Routes']['Properties']['RouteTableId'],{'Ref':'PrivateRoutes'})
        self.assertEqual(r['Db2Routes']['Properties']['RouteTableId'],{'Ref':'PrivateRoutes'})
        self.assertFalse(any(v['Type']=='AWS::EC2::Route' and v['Properties']['RouteTableId']=={'Ref':'PrivateRoutes'} for v in r.values()))
    def test_regional_worker_policies_have_no_home_workload_arns_and_snapshot_tags_survive(self):
        result=sample(); text=json.dumps(result['worker_policies'])
        self.assertNotIn('redshift',text);self.assertNotIn('${AWS::',text);self.assertNotIn('arn:aws:ec2:'+HOME,text)
        rows=[s for p in result['worker_policies'] for s in p['Statement']]
        snapshot=next(s for s in rows if s['Action']=='ec2:DeleteSnapshot')
        self.assertIn(TARGET,snapshot['Resource']);self.assertEqual(snapshot['Condition']['StringEquals']['ec2:Owner'],ACCOUNT)
        self.assertIn('ec2:ResourceTag/cloudhub:recovery',snapshot['Condition']['StringLike'])
        self.assertIn('ec2:ResourceTag/cloudhub:owner',snapshot['Condition']['Null'])
    def test_application_boundary_keeps_management_region_and_workload_services_are_regional(self):
        result=sample();r=result['template']['Resources'];text=json.dumps(r)
        self.assertNotIn('redshift',text)
        self.assertEqual(r['EnvironmentCfRole']['Properties']['PermissionsBoundary'],{'Ref':'DeploymentBoundary'})
        boundary=r['EnvironmentBoundary']['Properties']['PolicyDocument']
        management=next(s for s in boundary['Statement'] if s['Action']=='dynamodb:GetItem')
        self.assertEqual(management['Resource'],'arn:aws:dynamodb:'+HOME+':'+ACCOUNT+':table/control')
        policies=[v['Properties']['PolicyDocument'] for k,v in r.items() if k.startswith('EnvironmentPolicy')]
        rows=[s for p in policies for s in p['Statement']]
        self.assertTrue(any('apigateway:TagResource' in s['Action'] and '/apis*' in json.dumps(s['Resource']) for s in rows if isinstance(s['Action'],list)))
        creation=next(s for s in rows if s['Action']=='iam:CreateRole')
        self.assertEqual(creation['Condition']['ArnEquals']['iam:PermissionsBoundary'],{'Ref':'EnvironmentBoundary'})
        passed=next(s for s in rows if s['Action']=='iam:PassRole' and 'ec2.amazonaws.com' in json.dumps(s.get('Condition')) and 'lambda.amazonaws.com' in json.dumps(s.get('Condition')))
        self.assertIn('ecs-tasks.amazonaws.com',json.dumps(passed));self.assertNotIn('redshift.amazonaws.com',json.dumps(passed))
    def test_policy_documents_fit_limits_and_no_region_is_enabled_by_preparation(self):
        for region in ['ap-northeast-1','us-east-1']:
            result=sample(region);self.assertFalse(result['security_review']['new_workload_gates_enabled'])
            policies=result['worker_policies']+result['api_policies']+[v['Properties']['PolicyDocument'] for v in result['template']['Resources'].values() if v['Type']=='AWS::IAM::ManagedPolicy']
            for policy in policies:self.assertLessEqual(len(json.dumps(policy,separators=(',',':'))),6144)
        for region in ['ap-southeast-1','eu-west-1','us-east-1-bos-1a']:
            with self.assertRaises(ValueError):sample(region)

if __name__=='__main__':unittest.main()
