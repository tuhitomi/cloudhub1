"""LOCAL MOCK only: matrix, provenance, regional clients, owner and workflow fences."""
import json,sys,unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from cloudhub.regions import REGIONS,RegionRegistry,record_region,regional_settings,client_region
from cloudhub.catalog import configuration,configuration_key,ACTIVE_TEMPLATES
from cloudhub.cost import Estimator
from cloudhub.errors import HubError
from cloudhub.service import Service,record
from cloudhub.store import MemoryStore
from cloudhub.worker import Worker
from cloudhub.ui_context import context,locale_for_country,preference
from test_processors import rates,S
from test_domain import Driver
from generate_infra import build_template
HOME='ap-southeast-1';TARGET='ap-northeast-1'

def setup():
    home=rates();other={**rates(),'region':TARGET,'units':{k:'0.04' for k in rates()['units']}}
    home['regional_rates']={TARGET:other}
    policy={'control_region':HOME,'regions':{TARGET:{'prepared':True,'enabled':True,'verifications':{
        configuration_key('T07',configuration('T07')):{'passed':True,'region':TARGET,'provisioning_checks':2,'backup_restore_verified':True}}}}}
    return Service(MemoryStore(),clock=lambda:1000,estimator=Estimator(home),verified=ACTIVE_TEMPLATES,budget_milliusd=1000000,regions_config=policy, require_quotes=False)

class RegionsTests(unittest.TestCase):
    def test_home_additive_configuration_shard_preserves_legacy_price_proofs(self):
        from cloudhub.catalog import configuration_profiles
        service=setup();cfg=next(p['configuration'] for p in configuration_profiles('T07') if p['id']=='expanded')
        self.assertFalse(service.configuration_is_verified('T07',cfg,HOME))
        service.regions_config['regions'][HOME]={'enabled':True,'verifications':{configuration_key('T07',cfg):{'passed':True,'provisioning_checks':2,'backup_restore_verified':True}}}
        self.assertTrue(service.configuration_is_verified('T07',cfg,HOME))
        self.assertTrue(service.configuration_is_verified('T07',configuration('T07'),HOME))
        service.regions_config['regions'][HOME]['enabled']=False
        self.assertFalse(service.configuration_is_verified('T07',cfg,HOME))
    def test_only_three_commercial_regions_and_no_new_region_open_without_proof(self):
        service=setup();options=service.region_registry().options('T07',service.verified)
        self.assertEqual(set(r['region'] for r in options),set(REGIONS))
        self.assertTrue(options[1]['configuration_options'][0]['create_enabled'])
        self.assertFalse(options[1]['configuration_options'][1]['create_enabled'])
        self.assertEqual(options[2]['status'],'UNAVAILABLE')
        for value in ['eu-west-1','us-east-1-bos-1a','ap-northeast-1-wl1-nrt-wlz-1','arn:aws:outposts:us-east-1:123:outpost/a',{},'']:
            with self.assertRaises(HubError):service.region_registry().select(value)
    def test_region_configuration_and_prices_rechecked_at_create(self):
        service=setup()
        for body in [dict(template_id='T01',region=TARGET,duration_hours=1),dict(template_id='T07',region=TARGET,duration_hours=1,configuration={'max_files':999}),dict(template_id='T10',region=HOME,duration_hours=1)]:
            with self.assertRaises(HubError):service.create('alice','bad_region_',body)
        service.estimator.rates['regional_rates'][TARGET]['approved']=False
        with self.assertRaises(HubError):service.create('alice','bad_prices_',dict(template_id='T07',region=TARGET,duration_hours=1))
    def test_regional_estimates_differ_and_missing_region_has_no_home_prices(self):
        service=setup();a=service.estimator_for(HOME).estimate('T07',1);b=service.estimator_for(TARGET).estimate('T07',1)
        self.assertEqual(b['region'],TARGET);self.assertEqual(b['currency'],'USD');self.assertGreater(b['total_milliusd'],a['total_milliusd'])
        other=service.estimator_for('us-east-1').estimate('T07',1)
        self.assertFalse(other['approved']);self.assertIsNone(other['total_milliusd']);self.assertEqual(other['region'],'us-east-1')
    def test_full_fake_workflow_preserves_region_through_backup_restore_and_retire(self):
        service=setup();driver=Driver();seen=[]
        for name in ['create','created','ready','schedule','backup','resume','delete','audit','cancel_schedule']:
            original=getattr(driver,name)
            setattr(driver,name,lambda env,*args,_fn=original,_name=name:(seen.append((_name,env['region'])),_fn(env,*args))[1])
        worker=Worker(service,driver)
        def run(op):
            for _ in range(20):
                if worker.tick(op['operation_id'])['done']:return
            self.fail('Workflow did not finish')
        op=service.create('alice','regional_create',dict(template_id='T07',region=TARGET,duration_hours=1));run(op)
        env=service.owned('E',op['environment_id'],'alice');self.assertEqual(env['region'],TARGET)
        backup=service.command('alice',env['environment_id'],'backup','regional_backup');run(backup)
        rp=service.owned('R',backup['recovery_point'],'alice');self.assertEqual(rp['region'],TARGET)
        with self.assertRaises(HubError):service.create('alice','wrong_restore_',dict(template_id='T07',duration_hours=1,region=HOME,recovery_point=rp['recovery_point']))
        restored=service.create('alice','regional_restore',dict(template_id='T07',duration_hours=1,recovery_point=rp['recovery_point']));run(restored)
        run(service.command('alice',env['environment_id'],'destroy','regional_delete'))
        self.assertTrue(seen);self.assertTrue(all(region==TARGET for _,region in seen));self.assertEqual(service.owned('E',env['environment_id'],'alice')['status'],'DELETED')
    def test_legacy_provenance_is_required_and_conflicting_arns_are_rejected(self):
        with self.assertRaises(HubError):record_region({'environment_id':'old'}, {'region':HOME})
        self.assertEqual(record_region({'estimate':{'region':HOME}},{}),HOME)
        self.assertEqual(record_region({'stack_id':'arn:aws:cloudformation:'+TARGET+':123:stack/cloudhub/a'},{}),TARGET)
        with self.assertRaises(HubError):record_region({'region':HOME,'source':'arn:aws:rds:'+TARGET+':123:db/a'}, {})
        with self.assertRaises(HubError):record_region({}, {'legacy_region_binding':{'region':HOME,'verified':False}})
    def test_foreign_owner_cannot_use_region_or_recovery_to_bypass_ownership(self):
        service=setup();op=service.create('alice','owned_region_',dict(template_id='T07',region=TARGET,duration_hours=1))
        with self.assertRaises(HubError) as e:service.owned('E',op['environment_id'],'bob')
        self.assertEqual(e.exception.status,404)
        operation=service.store.get('O#'+op['operation_id']);operation['region']=HOME;service.save(operation)
        driver=Driver()
        with self.assertRaises(HubError):Worker(service,driver).tick(op['operation_id'])
        self.assertEqual(driver.calls,[])
    def test_recovery_parent_inheritance_checks_native_arn_too(self):
        service=setup();env=record('environment','old','alice',environment_id='old',region=HOME)
        rp=record('recovery','rp-old','alice',environment_id='old',source='arn:aws:rds:'+TARGET+':123:snapshot/a')
        service.save(env,rp)
        with self.assertRaises(HubError):service.region_for(service.store.get(rp['pk']))
    def test_nonhome_does_not_reuse_home_ami_network_or_backup_bucket(self):
        base={**S,'regions':{TARGET:{'region':TARGET,'prepared':True,'cf_role_arn':S['cf_role_arn'],'s3_backup_bucket':'tokyo-backup'}}}
        regional=regional_settings(base,{'region':TARGET})
        self.assertNotIn('ami_id',regional);self.assertNotIn('vpc_id',regional);self.assertEqual(regional['s3_backup_bucket'],'tokyo-backup')
        self.assertEqual(regional['management_table_arn'],S['management_table_arn']);self.assertEqual(client_region('scheduler',regional),HOME)
        self.assertEqual(client_region('rds',regional),TARGET);self.assertEqual(client_region('cloudfront',regional),'us-east-1')
    def test_clients_are_created_in_target_region_and_global_clients_are_separate(self):
        from cloudhub.s3_driver import S3Driver
        calls=[]
        with patch('boto3.client',side_effect=lambda name,**kw:calls.append((name,kw['region_name'])) or object()):
            S3Driver({**S,'region':TARGET,'control_region':HOME})
        self.assertIn(('s3',TARGET),calls);self.assertIn(('cloudformation',TARGET),calls);self.assertIn(('scheduler',HOME),calls)
    def test_matrix_cannot_reuse_proof_from_another_region(self):
        service=setup();proof=service.regions_config['regions'][TARGET]['verifications'][configuration_key('T07',configuration('T07'))];proof['region']=HOME
        self.assertFalse(service.configuration_is_verified('T07',configuration('T07'),TARGET))
    def test_regional_quote_preserves_shared_control_log_price_scope(self):
        service=setup();rates=service.estimator.rates['regional_rates'][TARGET]
        rates.update(control_region=HOME,unit_regions={'logs_gib':HOME,'control_plane_session':HOME})
        rates['units']['logs_gib']='0.76'
        quote=service.estimator_for(TARGET).estimate('T07',1)
        self.assertEqual(quote['region'],TARGET)
        self.assertEqual(quote['unit_regions']['s3_gib_month'],TARGET)
        self.assertEqual(quote['unit_regions']['logs_gib'],HOME)
        self.assertEqual(quote['unit_regions']['control_plane_session'],HOME)
        self.assertEqual(quote['lines']['logs'],'0.076')
        self.assertNotIn('ec2_hour',quote['units'])
        self.assertNotIn('Redshift',quote['assumptions']['cost_bound'])
        cdn=service.estimator_for(TARGET).estimate('T02',1)
        self.assertIn('US-DataTransfer-Out-Bytes',cdn['assumptions']['cloudfront_pricing_scope'])
        self.assertEqual(cdn['unit_regions']['cloudfront_transfer_gib'],'global')
    def test_workload_log_override_does_not_change_shared_workflow_log_rates(self):
        service=setup();rates=service.estimator.rates['regional_rates'][TARGET]
        rates.update(control_region=HOME,unit_regions={'logs_gib':HOME,'control_plane_session':HOME},
            template_rate_overrides={'T09':{'units':{'logs_gib':'0.76'},'unit_regions':{'logs_gib':TARGET}}})
        rates['units']['logs_gib']='0.70'
        workload=service.estimator_for(TARGET).estimate('T09',1)
        shared=service.estimator_for(TARGET).estimate('T07',1)
        self.assertEqual(workload['units']['logs_gib'],'0.76');self.assertEqual(workload['unit_regions']['logs_gib'],TARGET)
        self.assertEqual(workload['lines']['logs'],'0.076')
        self.assertEqual(shared['units']['logs_gib'],'0.70');self.assertEqual(shared['unit_regions']['logs_gib'],HOME)
        self.assertEqual(rates['units']['logs_gib'],'0.70')

class CountryAndLanguageTests(unittest.TestCase):
    def test_all_requested_country_mappings_and_english_fallback(self):
        for country,language in {'VN':'vi','JP':'ja','KR':'ko','CN':'zh-Hans','FR':'fr','DE':'de','ES':'es',None:'en','US':'en','XX':'en'}.items():self.assertEqual(locale_for_country(country),language)
    def test_direct_api_spoof_cannot_set_country(self):
        event={'headers':{'CloudFront-Viewer-Country':'VN','X-CloudHub-Edge-Key':'fake'}}
        self.assertEqual(context(event,'a'*32)['suggested_language'],'en');self.assertIsNone(context(event,'a'*32)['country_code'])
        event['headers']['X-CloudHub-Edge-Key']='a'*32;trusted=context(event,'a'*32)
        self.assertEqual(trusted['country_code'],'VN');self.assertNotIn('ip',json.dumps(trusted));self.assertNotIn('a'*32,json.dumps(trusted))
    def test_preferences_only_update_owned_language_never_role_or_quota(self):
        service=setup();profile=record('user','alice','alice',language_preference='auto',max_active=2,role='user');service.save(profile)
        self.assertEqual(preference(service,'alice',{'language':'ja'})['language_preference'],'ja')
        with self.assertRaises(HubError):preference(service,'alice',{'language':'en','role':'admin'})
        with self.assertRaises(HubError):preference(service,'alice',{'language':'xx'})
        with self.assertRaises(HubError):preference(service,'bob',{'language':'vi'})
        self.assertEqual(service.store.get('U#alice')['role'],'user');self.assertEqual(service.store.get('U#alice')['max_active'],2)
    def test_cloudfront_route_does_not_forward_identity_and_disables_cache(self):
        template=build_template();r=template['Resources'];behavior=r['FrontendDistribution']['Properties']['DistributionConfig']['CacheBehaviors'][0]['Fn::If'][1]
        self.assertEqual(behavior['PathPattern'],'/ui-context');self.assertEqual(behavior['CachePolicyId'],'4135ea2d-6df8-44a3-9df3-4b5a84be39ad')
        policy=r['UiCountryOriginPolicy']['Properties']['OriginRequestPolicyConfig'];self.assertEqual(policy['HeadersConfig']['Headers'],['CloudFront-Viewer-Country']);self.assertEqual(policy['CookiesConfig']['CookieBehavior'],'none')
        self.assertEqual(r['ApiFunction']['Properties']['Events']['UiContext']['Properties']['Auth']['Authorizer'],'NONE');self.assertTrue(template['Parameters']['UiEdgeSecret']['NoEcho'])
    def test_late_preference_request_cannot_overwrite_newer_choice(self):
        service=setup();service.save(record('user','alice','alice'))
        preference(service,'alice',{'language':'ja'},2000)
        result=preference(service,'alice',{'language':'vi'},1000)
        self.assertEqual(result['language_preference'],'ja');self.assertEqual(service.store.get('U#alice')['language_preference'],'ja')
    def test_regional_t07_grants_are_opt_in_size_bounded_and_exclude_compute(self):
        template=build_template();self.assertEqual(template['Parameters']['EnableRegionalT07']['Default'],'false')
        resources=template['Resources'];roles={
            'RegionalS3EnvironmentPolicy':{'EnvironmentCfRole'},
            'RegionalS3WorkerPolicy':{'WorkerFunctionRole','SweepFunctionRole'},
            'RegionalS3ApiPolicy':{'ApiFunctionRole'}}
        for name,expected_roles in roles.items():
            resource=resources[name];self.assertEqual(resource['Condition'],'HasRegionalT07')
            self.assertEqual({r['Ref'] for r in resource['Properties']['Roles']},expected_roles)
            policy=resource['Properties']['PolicyDocument'];self.assertLess(len(json.dumps(policy,separators=(',',':'))),6144)
            for row in policy['Statement']:
                actions=row['Action'] if isinstance(row['Action'],list) else [row['Action']]
                self.assertTrue(all(a.startswith(('s3:','cloudformation:')) for a in actions))
                for arn in row['Resource']:
                    text=arn['Fn::Sub'];self.assertIn('${AWS::AccountId}',text)
                    self.assertTrue(any(region in text for region in ('ap-northeast-1','us-east-1')))
                    self.assertNotIn('snapshot',text)
