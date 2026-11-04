"""Local/mocked SDK checks, never an AWS lifecycle or load test."""
import json,sys,unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock,patch
from botocore.exceptions import ClientError
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'scripts')]
from cloudhub.template_view import read,projection,HIDDEN
from cloudhub.errors import HubError
from test_regions import setup
from test_processors import S
from cloudhub.catalog import configuration_profiles

EID='env-'+'a'*24
ACCOUNT='123456789012'
def fixture(region='ap-southeast-1'):
    service=setup();env={'pk':'E#'+EID,'kind':'environment','owner_id':'alice','environment_id':EID,'template_id':'T05','region':region,'status':'READY'}
    service.store.rows[env['pk']]=env
    arn=f'arn:aws:cloudformation:{region}:{ACCOUNT}:stack/cloudhub-{EID}/00000000-0000-0000-0000-000000000000'
    cf=Mock();cf.describe_stacks.return_value={'Stacks':[{'StackName':'cloudhub-'+EID,'StackId':arn,'Tags':[{'Key':'cloudhub:owner','Value':'alice'},{'Key':'cloudhub:environment','Value':EID}]}]}
    cf.get_template.return_value={'TemplateBody':{'Resources':{'Machine':{'Type':'AWS::EC2::Instance','Properties':{'InstanceType':'t3.micro','UserData':{'Fn::Base64':'private bootstrap'}}}}}}
    return service,env,cf,arn

class TemplateViewTests(unittest.TestCase):
    def test_owned_actual_stack_not_a_regenerated_builder(self):
        s,e,cf,arn=fixture();before=deepcopy(s.store.rows)
        result=read(s,'alice',EID,S,cf)
        cf.get_template.assert_called_once_with(StackName=arn,TemplateStage='Original')
        self.assertEqual(result['source'],'AWS_CLOUDFORMATION_ORIGINAL');self.assertFalse(result['deployable'])
        self.assertEqual(result['template']['Resources']['Machine']['Properties']['InstanceType'],'t3.micro')
        self.assertNotIn('private bootstrap',json.dumps(result));self.assertEqual(before,s.store.rows)
    def test_owner_denied_before_config_or_sdk(self):
        s,e,cf,arn=fixture()
        with patch('cloudhub.runtime.driver_settings') as settings,patch('boto3.client') as client:
            with self.assertRaises(HubError) as caught:read(s,'other',EID)
            self.assertEqual(caught.exception.code,'NOT_FOUND');settings.assert_not_called();client.assert_not_called()
    def test_backend_uses_persisted_region_for_all_three_regions(self):
        for region in ['ap-southeast-1','ap-northeast-1','us-east-1']:
            s,e,cf,arn=fixture(region)
            with patch('boto3.client',return_value=cf) as client:
                result=read(s,'alice',EID,S)
                self.assertEqual(client.call_args.kwargs['region_name'],region);self.assertEqual(result['region'],region)
    def test_missing_legacy_region_does_not_guess_location(self):
        s,e,cf,arn=fixture();del e['region']
        with self.assertRaises(HubError) as caught:read(s,'alice',EID,S,cf)
        self.assertEqual(caught.exception.code,'REGION_PROVENANCE_REQUIRED');cf.describe_stacks.assert_not_called()
    def test_forged_arn_and_wrong_tags_cannot_read_another_stack(self):
        for bad in ['arn:aws:cloudformation:us-east-1:123456789012:stack/cloudhub-'+EID+'/id', 'arn:aws:cloudformation:ap-southeast-1:999999999999:stack/cloudhub-'+EID+'/id']:
            s,e,cf,arn=fixture();e['stack_id']=bad
            with self.assertRaises(HubError):read(s,'alice',EID,S,cf)
            cf.get_template.assert_not_called();cf.describe_stacks.assert_not_called()
        s,e,cf,arn=fixture();cf.describe_stacks.return_value['Stacks'][0]['Tags'][0]['Value']='other'
        with self.assertRaises(HubError):read(s,'alice',EID,S,cf)
        cf.get_template.assert_not_called()
    def test_deleted_stack_requires_validated_saved_arn(self):
        s,e,cf,arn=fixture();e.update(status='DELETED',stack_id=arn)
        self.assertTrue(read(s,'alice',EID,S,cf)['read_only']);cf.describe_stacks.assert_called_once_with(StackName=arn)
    def test_all_sensitive_and_unknown_sections_fail_closed(self):
        sentinel='CANARY_SECRET_DO_NOT_RETURN'
        document={'Metadata':{'raw':sentinel},'Outputs':{'Leak':{'Value':sentinel}},'Mappings':{'a':sentinel},'Conditions':{'x':sentinel},
            'Parameters':{'Password':{'Type':'String','NoEcho':True,'Default':sentinel},'Payload':{'Type':'String','Default':sentinel}},
            'Resources':{'Machine':{'Type':'AWS::EC2::Instance','Metadata':{'raw':sentinel},'Properties':{'UserData':{'Fn::Base64':sentinel},'InstanceType':'t3.micro','Tags':[{'Key':'secret','Value':sentinel}]}},
                'Function':{'Type':'AWS::Lambda::Function','Properties':{'Code':{'ZipFile':sentinel},'Environment':{'Variables':{'PASSWORD':sentinel}},'MemorySize':128,'FutureField':sentinel}},
                'Secret':{'Type':'AWS::SecretsManager::Secret','Properties':{'SecretString':sentinel}},
                'Unknown':{'Type':'AWS::Future::Resource','Properties':{'NewField':{'Inner':sentinel}}}}}
        projected,summary,count,omitted=projection(document)
        self.assertNotIn(sentinel,json.dumps(projected));self.assertEqual(len(summary),4);self.assertGreater(count,5)
        self.assertIn('Outputs',omitted);self.assertNotIn('Default',projected['Parameters']['Password'])
        self.assertEqual(projected['Resources']['Function']['Properties']['MemorySize'],128)
        self.assertEqual(projected['Resources']['Function']['Properties']['FutureField'],HIDDEN)
    def test_sanitizer_accepts_actual_generated_templates_for_all_nine(self):
        from cloudhub.templates import linux_template
        from cloudhub.s3_template import s3_template
        from cloudhub.rds_template import rds_template
        from cloudhub.ecs_template import ecs_template
        from cloudhub.efs_template import efs_template
        from cloudhub.data_template import data_template
        builders={'T01':linux_template,'T02':s3_template,'T03':rds_template,'T04':rds_template,'T05':linux_template,'T06':ecs_template,'T07':s3_template,'T08':efs_template,'T09':data_template}
        settings={**S,'availability_zone':'ap-southeast-1a','ssh_cidr':'192.0.2.1/32'}
        for tid,build in builders.items():
            with self.subTest(template=tid):
                env={'environment_id':EID,'owner_id':'alice','template_id':tid,'configuration':configuration_profiles(tid)[0]['configuration']}
                original=build(env,settings);view,rows,count,omitted=projection(original)
                self.assertEqual(set(view['Resources']),set(original['Resources']));self.assertEqual(len(rows),len(original['Resources']))
                self.assertNotIn('Fn::Base64',json.dumps(view));self.assertNotIn('ZipFile',json.dumps(view))
    def test_service_errors_never_return_raw_aws_message_or_fallback(self):
        for code,expected in [('ValidationError','TEMPLATE_UNAVAILABLE'),('AccessDenied','TEMPLATE_ACCESS_UNAVAILABLE'),('Throttling','TEMPLATE_TEMPORARILY_UNAVAILABLE')]:
            s,e,cf,arn=fixture();cf.get_template.side_effect=ClientError({'Error':{'Code':code,'Message':'PRIVATE_BACKEND_CANARY'}},'GetTemplate')
            with self.assertRaises(HubError) as caught:read(s,'alice',EID,S,cf)
            self.assertEqual(caught.exception.code,expected);self.assertNotIn('PRIVATE_BACKEND_CANARY',str(caught.exception))
    def test_yaml_and_oversized_body_fail_safely(self):
        for original in ['Resources:\n  X: yaml', ' '*1048577]:
            s,e,cf,arn=fixture();cf.get_template.return_value={'TemplateBody':original}
            with self.assertRaises(HubError) as caught:read(s,'alice',EID,S,cf)
            self.assertEqual(caught.exception.code,'TEMPLATE_FORMAT_UNSUPPORTED')
    def test_iac_has_only_scoped_read_actions_and_authenticated_route(self):
        from generate_infra import build_template
        from template_view_infra import extend_native,PATH
        doc=build_template();policy=doc['Resources']['TemplateViewReadPolicy']['Properties'];stmt=policy['PolicyDocument']['Statement'][0]
        self.assertEqual(stmt['Action'],['cloudformation:DescribeStacks','cloudformation:GetTemplate']);self.assertEqual(len(stmt['Resource']),3)
        self.assertTrue(all(':stack/cloudhub-env-*/*' in x['Fn::Sub'] for x in stmt['Resource']))
        event=doc['Resources']['ApiFunction']['Properties']['Events']['TemplateView'];self.assertEqual(event['Properties']['Method'],'GET');self.assertNotIn('Auth',event['Properties'])
        native={'Resources':{'ApiFunction':{'Type':'AWS::Lambda::Function'},'HttpApi':{'Properties':{'Body':{'paths':{'/environments/{environment_id}':{'get':{'security':[{'jwt':[]}]}}}}}},'HttpApiApiGatewayDefaultStage':{'Properties':{}}}}
        extend_native(native);self.assertTrue(native['Resources']['HttpApi']['Properties']['Body']['paths'][PATH]['get']['security'])
        self.assertEqual(extend_native(deepcopy(native)),native)
    def test_api_retains_jwt_no_store_and_rejects_region_override(self):
        from cloudhub import api
        s,e,cf,arn=fixture();path='/environments/'+EID+'/template'
        event={'rawPath':path,'requestContext':{'http':{'method':'GET'},'authorizer':{'jwt':{'claims':{'sub':'alice','username':'alice','token_use':'access'}}}}}
        identity={'owner_id':'alice','email':'alice@example.invalid','email_verified':True,'enabled':True}
        with patch.object(api,'SERVICE',s),patch.object(api,'DISPATCH',None),patch('cloudhub.accounts.Accounts') as accounts,patch('cloudhub.registration.ensure_profile',return_value={}),patch('cloudhub.template_view.read',return_value={'read_only':True}) as reader,patch.dict('os.environ',{'USER_POOL_ID':'local'}):
            accounts.return_value.identity.return_value=identity
            result=api.handler(event);self.assertEqual(result['statusCode'],200);self.assertEqual(result['headers']['cache-control'],'no-store');reader.assert_called_once_with(s,'alice',EID)
            reader.reset_mock();result=api.handler({**event,'queryStringParameters':{'region':'us-east-1'}});self.assertEqual(result['statusCode'],400);reader.assert_not_called()
            result=api.handler({**event,'requestContext':{'http':{'method':'GET'}}});self.assertEqual(result['statusCode'],401)

if __name__=='__main__':unittest.main()
