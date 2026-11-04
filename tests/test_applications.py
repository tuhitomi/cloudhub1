"""LOCAL only; application native gate stays closed without its own proof."""
import json,unittest,sys
from pathlib import Path
from copy import deepcopy
from unittest.mock import Mock,patch
from cloudhub.applications import normalize,revision,options,begin,request_value
from cloudhub.content_app import render
from cloudhub.application_driver import deploy,node_script
from cloudhub.errors import HubError
from cloudhub.quotes import fingerprint
from cloudhub.rds_template import rds_template,user_data
from cloudhub.worker import Worker
from test_recommendations import setup,HOME
from test_processors import S

def app(release='content-site-1',title='My project'):return {'release_id':release,'revision':revision(release),'title':title,'subtitle':'Student content site','language':'vi'}
def enabled():
 from cloudhub.catalog import configuration_key,resolve_configuration
 s=setup();s.require_quotes=True;s.regions_config['application_releases']={HOME:{t:{r:{'passed':True,'revision':revision(r),'data_verified':True,'rollback_verified':True,'configuration_keys':[configuration_key(t,resolve_configuration(t,None))]} for r in ['content-site-1','content-site-2']} for t in ['T03','T04']}};return s
def create(s,tid='T03'):
 body={'template_id':tid,'region':HOME,'duration_hours':1,'application':app()};q=s.create_estimate('alice',body);op=s.create('alice','application-create-01',{**body,'quote_id':q['quote_id']});env=s.store.get('E#'+op['environment_id']);env.update(status='READY',lock=None,application_history=[]);s.save(env);return s.store.get(env['pk'])

class ApplicationTests(unittest.TestCase):
 def test_worker_checkpoint_then_final_save_uses_persisted_versions(self):
  s=enabled();env=create(s);body={'application':app('content-site-2'),'expected_revision':env['lifecycle_revision'],'expected_application_revision':fingerprint(env['application']),'confirmed':True};op=begin(s,'alice',env['environment_id'],'checkpoint-app-01',body)
  driver=Mock(spec=['deploy_application'])
  def step(environment,operation,before_mutation):
   operation['application_step']='WAIT_BOOTSTRAP';before_mutation()
   operation['bootstrap_accepted']=True;before_mutation()
   operation['application_step']='APPLY_NODES';return False
  driver.deploy_application.side_effect=step
  result=Worker(s,driver).tick(op['operation_id']);self.assertFalse(result['done']);saved=s.store.get(op['pk']);self.assertEqual(saved['application_step'],'APPLY_NODES');self.assertTrue(saved['bootstrap_accepted']);self.assertEqual(s.store.get(env['pk'])['lock'],op['operation_id'])
 def test_publication_checkpoint_also_keeps_optimistic_fence_for_final_save(self):
  s=enabled();env=create(s);body={'application':app('content-site-2'),'expected_revision':env['lifecycle_revision'],'expected_application_revision':fingerprint(env['application']),'confirmed':True};op=begin(s,'alice',env['environment_id'],'publication-checkpoint-01',body);op['phase']='PUBLISH_RELEASE';s.save(op)
  def publish(driver,environment,operation,before_switch):
   operation['cf_switch_attempted']=True;before_switch();operation['public_verify_cursor']=0;return False
  with patch('cloudhub.releases.publish',side_effect=publish):result=Worker(s,Mock(spec=[])).tick(op['operation_id'])
  self.assertFalse(result['done']);self.assertTrue(s.store.get(op['pk'])['cf_switch_attempted']);self.assertEqual(s.store.get(op['pk'])['public_verify_cursor'],0)
 def test_optional_bootstrap_iam_remains_singapore_owned_and_userdata_only(self):
  sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
  from recommendation_infra import extend
  template={'Parameters':{},'Resources':{'ApiFunction':{'Properties':{'Environment':{'Variables':{}},'Events':{}}}}};extend(template)
  self.assertEqual(template['Parameters']['ApplicationBootstrapPermissionsEnabled']['Default'],'false')
  policy=template['Resources']['ReviewedApplicationBootstrapAccess'];self.assertEqual(policy['Condition'],'EnableApplicationBootstrapPermissions');self.assertEqual(policy['Properties']['Roles'],[{'Ref':'EnvironmentCfRole'}])
  statements=policy['Properties']['PolicyDocument']['Statement'];actions=[]
  for statement in statements:
   action=statement['Action'];actions.extend(action if isinstance(action,list) else [action])
   self.assertIn(':ap-southeast-1:${AWS::AccountId}:',statement['Resource']['Fn::Sub']);self.assertEqual(statement['Condition']['StringEquals']['aws:RequestedRegion'],'ap-southeast-1')
   self.assertEqual(statement['Condition']['Null']['aws:ResourceTag/cloudhub:owner'],'false');self.assertEqual(statement['Condition']['StringEquals']['aws:ResourceTag/cloudhub:managed'],'true');self.assertEqual(statement['Condition']['StringLike']['aws:ResourceTag/cloudhub:environment'],'env-*')
  self.assertEqual(set(actions),{'ec2:StopInstances','ec2:StartInstances','ec2:ModifyInstanceAttribute','ec2:CreateLaunchTemplateVersion'})
  self.assertEqual(statements[1]['Condition']['Null']['ec2:Attribute/UserData'],'false')
  self.assertNotIn('ec2:Attribute',statements[1]['Condition']['StringEquals'])
 def test_reviewed_application_cloudformation_create_restore_variants_lint(self):
  from cfnlint.api import lint
  for tid in ['T03','T04']:
   env={'template_id':tid,'owner_id':'alice','environment_id':'env-'+'a'*24,'application':normalize(app())}
   for recovery in [None,{'db_snapshot_id':'cloudhub-rp-'+'b'*24}]:
    built=rds_template(env,S,recovery);self.assertEqual(len(built['Parameters']),5)
    errors=[str(e) for e in lint(json.dumps(built),regions=['us-east-1']) if e.rule.id.startswith('E') or e.rule.id=='W3037'];self.assertEqual(errors,[],(tid,errors))
 def test_failed_application_retry_keeps_target_and_budget_but_reissues_only_failed_command(self):
  s=enabled();env=create(s);body={'application':app('content-site-2'),'expected_revision':env['lifecycle_revision'],'expected_application_revision':fingerprint(env['application']),'confirmed':True}
  op=begin(s,'alice',env['environment_id'],'retry-app-deploy-01',body);env=s.store.get(env['pk']);op['app_command_i-test']='failed-ssm-id';op['application_nodes']={'i-previous':True};s.save(op);Worker(s,Mock()).fail(op['operation_id'],'test node failure')
  before=s.store.get('Q#GLOBAL')['reserved_milliusd'];r=s.control_operation('alice',op['operation_id'],'retry','retry-app-step-01',{})
  self.assertNotIn('app_command_i-test',r);self.assertEqual(r['application_nodes'],{'i-previous':True});self.assertEqual(r['application_target']['release_id'],'content-site-2');self.assertEqual(s.store.get('Q#GLOBAL')['reserved_milliusd'],before)
 def test_persisted_dynamodb_decimal_schema_is_valid_json_for_bootstrap_and_deployment(self):
  import base64
  from boto3.dynamodb.types import TypeSerializer,TypeDeserializer
  from cloudhub.applications import configuration_json,deployment_parameters
  value=TypeDeserializer().deserialize(TypeSerializer().serialize(normalize(app())))
  self.assertEqual(json.loads(configuration_json(value))['data_schema'],1)
  built=user_data(S,value);self.assertEqual(built['Fn::Sub'][1]['ConfigBase64'],{'Ref':'CloudHubApplicationConfig'})
  parameters=deployment_parameters(value);config=json.loads(base64.b64decode(parameters['CloudHubApplicationConfig']));self.assertEqual(config['data_schema'],1)
  self.assertTrue(all(len(v.encode())<=4096 for v in parameters.values()))
  self.assertIn('application.json.pending',node_script(value,'op-'+'a'*24))
 def test_standard_application_proof_cannot_open_expanded_or_another_region(self):
  from cloudhub.catalog import configuration_profiles
  from cloudhub.applications import available
  s=enabled();expanded=next(p['configuration'] for p in configuration_profiles('T03') if p['id']=='expanded')
  self.assertTrue(available(s,'T03',HOME,'content-site-1'));self.assertFalse(available(s,'T03',HOME,'content-site-1',expanded));self.assertFalse(available(s,'T03','us-east-1','content-site-1'))
  self.assertEqual(options(s,'T03',HOME)[0]['configuration_ids'],['standard'])
 def test_bootstrap_and_each_t04_node_reconcile_before_success_and_retry_uses_one_stack_update(self):
  target=normalize(app());env={'template_id':'T04','owner_id':'alice','environment_id':'env-'+'a'*24};op={'operation_id':'op-'+'a'*24,'application_target':target,'application_step':'UPDATE_BOOTSTRAP'}
  from cloudhub.applications import deployment_parameters
  old=deployment_parameters(normalize(app('content-site-2')));present=[{'ParameterKey':k,'ParameterValue':v} for k,v in old.items()]+[{'ParameterKey':'UnrelatedSetting','ParameterValue':'keep'}]
  driver=Mock(unsafe=True);driver.settings=S;driver.stack_name.return_value='cloudhub-env-isolated';driver.assert_stack.return_value={'StackStatus':'UPDATE_COMPLETE','Parameters':present}
  self.assertFalse(deploy(driver,env,op));driver.cloudformation.update_stack.assert_called_once();self.assertEqual(op['application_step'],'WAIT_BOOTSTRAP')
  args=driver.cloudformation.update_stack.call_args.kwargs;self.assertTrue(args['UsePreviousTemplate']);self.assertNotIn('TemplateBody',args);self.assertIn({'ParameterKey':'UnrelatedSetting','UsePreviousValue':True},args['Parameters']);driver.cloudformation.get_template.assert_not_called()
  accepted=[{'ParameterKey':k,'ParameterValue':v} for k,v in deployment_parameters(target).items()]+[present[-1]]
  driver.assert_stack.return_value={'StackStatus':'UPDATE_IN_PROGRESS','Parameters':accepted};self.assertFalse(deploy(driver,env,op));driver.cloudformation.update_stack.assert_called_once()
  driver.assert_stack.return_value={'StackStatus':'UPDATE_COMPLETE','Parameters':accepted};self.assertFalse(deploy(driver,env,op));self.assertEqual(op['application_step'],'APPLY_NODES')
  driver.active_instances.return_value=[{'InstanceId':'i-first'},{'InstanceId':'i-second'}];driver.command.side_effect=[None,json.dumps({'application_revision':target['revision']}),json.dumps({'application_revision':target['revision']})]
  self.assertFalse(deploy(driver,env,op));self.assertFalse(deploy(driver,env,op));self.assertFalse(deploy(driver,env,op));self.assertTrue(deploy(driver,env,op));self.assertEqual(set(op['application_nodes']),{'i-first','i-second'})
  driver.active_instances.return_value=[{'InstanceId':'i-first'},{'InstanceId':'i-second'},{'InstanceId':'i-new'}]
  with self.assertRaises(HubError):deploy(driver,env,op)
 def test_worker_keeps_operation_owner_history_data_scope_and_late_callback_safe(self):
  s=enabled();env=create(s);body={'application':app('content-site-2'),'expected_revision':env['lifecycle_revision'],'expected_application_revision':fingerprint(env['application']),'confirmed':True}
  op=begin(s,'alice',env['environment_id'],'worker-app-update-01',body);driver=Mock(spec=['deploy_application']);driver.deploy_application.side_effect=[False,True]
  worker=Worker(s,driver);self.assertFalse(worker.tick(op['operation_id'])['done']);result=worker.tick(op['operation_id']);self.assertTrue(result['done'])
  updated=s.store.get(env['pk']);self.assertEqual(updated['application']['release_id'],'content-site-2');self.assertEqual(updated['application_history'][0]['application']['release_id'],'content-site-1');self.assertIsNone(updated['lock'])
  self.assertTrue(worker.tick(op['operation_id'])['done']);self.assertEqual(driver.deploy_application.call_count,2)
 def test_unreviewed_code_urls_and_revision_override_are_rejected(self):
  for bad in [{**app(),'url':'https://untrusted.invalid/app.py'},{**app(),'release_id':'arbitrary'},{**app(),'revision':'f'*64},{**app(),'release_id':{}},{**app(),'title':'bad\ntext'}]:
   with self.assertRaises(HubError):normalize(bad)
 def test_default_native_gate_is_closed_separately_from_infrastructure_gate(self):
  s=setup();self.assertFalse(any(v['enabled'] for v in options(s,'T03',HOME)))
  with self.assertRaises(HubError) as error:s.create_estimate('alice',{'template_id':'T03','duration_hours':1,'application':app()})
  self.assertEqual(error.exception.code,'APPLICATION_UNVERIFIED')
 def test_quote_binds_release_config_owner_and_retries_existing_operation(self):
  s=enabled();body={'template_id':'T03','duration_hours':1,'application':app()};q=s.create_estimate('alice',body)
  with self.assertRaises(HubError):s.create('alice','wrong-app-01',{**body,'application':app(title='Changed'),'quote_id':q['quote_id']})
  op=s.create('alice','same-app-01',{**body,'quote_id':q['quote_id']});self.assertEqual(s.create('alice','same-app-01',{**body,'quote_id':q['quote_id']})['operation_id'],op['operation_id'])
  self.assertEqual(s.store.get('E#'+op['environment_id'])['application']['title'],'My project')
  with self.assertRaises(HubError):s.create('bob','cross-app-01',{**body,'quote_id':q['quote_id']})
 def test_t03_t04_bootstrap_contains_reviewed_bytes_and_server_secret_only(self):
  for tid in ['T03','T04']:
   env={'template_id':tid,'owner_id':'alice','environment_id':'env-'+'a'*24,'application':normalize(app())};built=rds_template(env,S)
   props=built['Resources']['Instance']['Properties'] if tid=='T03' else built['Resources']['LaunchTemplate']['Properties']['LaunchTemplateData']
   text=json.dumps(props['UserData']);self.assertIn('CLOUDHUB_APP_CONFIG',text);self.assertIn('ConfigBase64',text)
   self.assertNotIn('password=',text);self.assertNotIn('APPLICATION_UNVERIFIED',text)
 def test_content_is_real_searchable_data_and_escapes_user_html(self):
  cfg=normalize(app(title='<script>not code</script>'));records=[{'record_id':'post-1','text':'Hello PostgreSQL'},{'record_id':'post-2','text':'Other'}]
  page=render(cfg,records,'/?q=PostgreSQL');self.assertIn('Hello PostgreSQL',page);self.assertNotIn('<p>Other</p>',page);self.assertNotIn('<script>not code</script>',page)
  self.assertIn('post-1',render(cfg,records,'/posts/post-1'));self.assertIsNone(render(cfg,records,'/posts/missing'))
 def test_deploy_is_owner_revision_locked_and_idempotent_without_new_reservation(self):
  s=enabled();env=create(s);before=s.store.get('Q#GLOBAL')['reserved_milliusd'];body={'application':app('content-site-2'),'expected_revision':env['lifecycle_revision'],'expected_application_revision':fingerprint(env['application']),'confirmed':True}
  with self.assertRaises(HubError):begin(s,'bob',env['environment_id'],'wrong-owner-01',body)
  op=begin(s,'alice',env['environment_id'],'deploy-release-01',body);self.assertEqual(op['phase'],'DEPLOY_APPLICATION');self.assertEqual(begin(s,'alice',env['environment_id'],'deploy-release-01',body)['operation_id'],op['operation_id'])
  self.assertEqual(before,s.store.get('Q#GLOBAL')['reserved_milliusd'])
  with self.assertRaises(HubError):begin(s,'alice',env['environment_id'],'deploy-concurrent-01',body)
 def test_restore_preserves_app_and_cannot_pick_a_different_release_or_owner(self):
  from cloudhub.applications import restore_inputs
  s=enabled();row={'pk':'R#rp-1','owner_id':'alice','kind':'recovery','recovery_point':'rp-1','application':normalize(app())};s.store.rows[row['pk']]=row
  self.assertEqual(restore_inputs(s,'alice',{'recovery_point':'rp-1'})['application']['title'],'My project')
  with self.assertRaises(HubError):restore_inputs(s,'bob',{'recovery_point':'rp-1'})
  with self.assertRaises(HubError):restore_inputs(s,'alice',{'recovery_point':'rp-1','application':app('content-site-2')})
 def test_unknown_bootstrap_and_failed_node_do_not_report_ready(self):
  env={'template_id':'T03','owner_id':'alice','environment_id':'env-'+'a'*24};op={'application_target':normalize(app()),'application_step':'WAIT_BOOTSTRAP','bootstrap_accepted':True}
  from cloudhub.applications import deployment_parameters
  driver=Mock(unsafe=True);driver.assert_stack.return_value={'StackStatus':'UPDATE_COMPLETE','Parameters':[{'ParameterKey':k,'ParameterValue':v} for k,v in deployment_parameters(normalize(app('content-site-2'))).items()]};driver.settings=S
  with self.assertRaises(HubError) as error:deploy(driver,env,op)
  self.assertEqual(error.exception.code,'APPLICATION_RECONCILE_REQUIRED')
  script=node_script(normalize(app()),'op-'+'a'*24);self.assertIn('sha256sum --check',script);self.assertIn('application-rollback',script);self.assertIn('internal/manifest',script);self.assertNotIn('get_secret_value',script)

if __name__=='__main__':unittest.main()
