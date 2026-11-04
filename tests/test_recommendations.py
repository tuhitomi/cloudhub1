"""LOCAL/MOCK only. These fixtures are not application load measurements."""
import json,os,sys,unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from test_regions import setup as base_setup,HOME,TARGET
def setup():
    service=base_setup();service.recommendations_enabled=True;return service
from cloudhub.workloads import SAMPLES,normalize,demand,resource_assessment
from cloudhub.recommendations import recommend,schema
from cloudhub.benchmarks import validate_report,admin_route,matching,capability_revision,summarize,OWNER
from cloudhub.catalog import configuration,configuration_profiles,configuration_key
from cloudhub.quotes import fingerprint
from cloudhub.errors import HubError

def request(tid='T07',**extra):return dict(mode='RECOMMEND',template_id=tid,region=HOME,estimate_hours=1,workload=SAMPLES[tid],**extra)
def fixture_report(tid='T07'):
    cfg=configuration(tid)
    return {'schema':1,'template_id':tid,'region':HOME,'configuration':cfg,'capability_revision':capability_revision(tid,cfg),
        'application':{'kind':'SAMPLE','revision':'a'*64,'dataset_revision':'b'*64},'scenario':{'id':'local-unit-fixture','revision':'c'*64,'workload_schema':'workload-1'},
        'workload':SAMPLES[tid],'infrastructure':{'configuration':cfg,'limits':{'source':'LOCAL_UNIT_FIXTURE'},'quota_snapshot':{'source':'LOCAL_UNIT_FIXTURE'},'application_artifact':'a'*64},
        'generator':{'location':'LOCAL_FIXTURE','tool':'unit-test','version':'1','cpu':1,'memory_mib':256,'model':'arrival-rate','max_concurrency':1},
        'execution':{'mode':'LOCAL_FIXTURE','environment_id':'env-local-unit','started_at':900,'ended_at':903,'duration_s':3,'warmup_s':0,'target_rate':1,'rate_unit':'transfers/s','dropped_iterations':0,'stop_reason':'COMPLETED'},
        'samples':[{'elapsed_ms':n,'ok':True,'bytes':1024,'correct':True} for n in [10,20,30]],
        'observations':{'cpu_credits_before':{'local':True},'cpu_credits_after':{'local':True},'cloudwatch':{'local':True},'scaling_timeline':[{'local':True}], 'cache_state':'WARM','data_correctness':True},
        'bottlenecks':['No conclusion: synthetic unit fixture'],'evidence_files':[{'name':'fixture.json','sha256':'d'*64}]}

class RecommendationTests(unittest.TestCase):
    def test_all_nine_have_distinct_inputs_working_pipeline_and_no_writes_or_fake_capacity(self):
        s=setup();before=deepcopy(s.store.rows);contract=schema(s)
        self.assertEqual(set(contract['templates']),set(SAMPLES))
        for tid in SAMPLES:
            with self.subTest(tid=tid):
                result=recommend(s,'alice',request(tid))
                self.assertTrue(result['read_only']);self.assertFalse(result['is_quote']);self.assertFalse(result['admission_checked'])
                self.assertEqual(result['status'],'OPTIONS');self.assertEqual(len(result['options']),1)
                self.assertIsNone(result['options'][0]['capacity']);self.assertEqual(result['options'][0]['evidence_level'],'RESOURCE_REQUIREMENTS')
                self.assertIn('planning_workload',result['options'][0]['creation_defaults'])
        self.assertEqual(before,s.store.rows)
        self.assertNotIn('active_users',{f['key'] for f in contract['templates']['T01']['fields']})
        self.assertNotIn('target_rps',{f['key'] for f in contract['templates']['T07']['fields']})
    def test_integer_units_and_unknown_are_not_implicit_zero(self):
        for value in [-1,1.5,True,'5',float('inf')]:
            with self.assertRaises(HubError):normalize('T07',{'data_kib':value})
        self.assertIsNone(normalize('T07',{})['data_kib'])
        for key in ['owner_id','verified','instance_type','target_url']:
            with self.assertRaises(HubError):normalize('T07',{key:'bad'})
    def test_demand_equations_do_not_become_capacity(self):
        w={**SAMPLES['T03'],'active_users':60,'actions_per_minute':2,'api_calls_per_action':3,'background_rps':4}
        self.assertEqual(demand('T03',normalize('T03',w),1)['target_rps'],'10')
        d=demand('T02',normalize('T02',SAMPLES['T02']),1)
        self.assertEqual(d['page_views'],'100');self.assertEqual(d['asset_requests'],'500');self.assertEqual(d['origin_requests'],'50')
        r=recommend(setup(),'alice',{**request('T03'),'workload':w})
        self.assertIsNone(r['options'][0]['capacity'])
    def test_t09_rejects_conflicting_user_and_direct_rate_and_honors_actual_gateway_limit(self):
        with self.assertRaises(HubError):recommend(setup(),'alice',{**request('T09'),'workload':{**SAMPLES['T09'],'active_users':60,'actions_per_minute':2,'api_calls_per_action':1,'background_rps':0}})
        r=recommend(setup(),'alice',{**request('T09'),'workload':{**SAMPLES['T09'],'target_rps':6}})
        self.assertEqual(r['status'],'NO_MATCH');self.assertEqual(r['options'],[])
        self.assertIn('API_RATE_LIMIT',json.dumps(r['excluded']))
    def test_worker_not_supported_and_wrong_template_fields_fail_closed(self):
        r=recommend(setup(),'alice',{**request('T06'),'workload':{**SAMPLES['T06'],'application_kind':'WORKER','jobs_per_second':1}})
        self.assertEqual(r['status'],'NO_MATCH');self.assertIn('WORKER_NOT_SUPPORTED',json.dumps(r['excluded']))
        for tid in SAMPLES:
            with self.assertRaises(HubError):recommend(setup(),'alice',{**request(tid),'workload':{'field_for_another_template':1}})
    def test_catalog_proof_region_and_feature_gates_are_authoritative(self):
        s=setup()
        for region in ['eu-west-1','us-east-1-bos-1a']:
            with self.assertRaises(HubError):recommend(s,'alice',{**request(),'region':region})
        r=recommend(s,'alice',{**request(),'region':'us-east-1'});self.assertFalse(r['options'])
        r=recommend(s,'alice',{**request(),'mode':'ASSESS','profile_id':'files'})
        self.assertEqual(r['assessment']['status'],'CONFIGURATION_UNAVAILABLE')
        with self.assertRaises(HubError):recommend(s,'alice',{**request(),'profile_id':'arbitrary-size'})
    def test_unknown_prices_and_budget_never_become_zero_or_a_free_tier_claim(self):
        s=setup();s.estimator.rates['approved']=False;r=recommend(s,'alice',request())
        self.assertEqual(len(r['options']),1);self.assertIsNone(r['options'][0]['cost']['total_milliusd']);self.assertEqual(r['options'][0]['budget_status'],'UNKNOWN')
        self.assertFalse(r['options'][0]['can_select'])
        r=recommend(setup(),'alice',request(budget_milliusd=0));self.assertEqual(r['status'],'NO_MATCH');self.assertEqual(r['options'][0]['budget_status'],'EXCEEDED')
    def test_cloudfront_viewer_scope_cannot_reuse_us_price_for_apac(self):
        r=recommend(setup(),'alice',{**request('T02'),'workload':{**SAMPLES['T02'],'viewer_geography':'APAC'}})
        self.assertIsNone(r['options'][0]['cost']['total_milliusd']);self.assertIn('cloudfront_viewer_APAC',json.dumps(r,default=str))
    def test_declared_traffic_changes_approved_estimate_and_fresh_quote_binds_workload(self):
        s=setup();s.require_quotes=True;tid='T05';r=recommend(s,'alice',request(tid));o=r['options'][0]
        body={'template_id':tid,'region':HOME,'estimate_hours':1,'configuration':o['configuration'],
              'operating_policy':{**o['creation_defaults']['operating_policy'],'confirmed':True},'planning_workload':o['creation_defaults']['planning_workload']}
        q=s.create_estimate('alice',body);changed={**body,'planning_workload':{**body['planning_workload'],'page_kib':1000},'quote_id':q['quote_id']}
        with self.assertRaises(HubError) as e:s.create('alice','changed-workload',changed)
        self.assertEqual(e.exception.code,'QUOTE_CHANGED')
        accepted=s.create('alice','same-workload-01',{**body,'quote_id':q['quote_id']});env=s.store.get('E#'+accepted['environment_id'])
        self.assertEqual(env['planning_workload']['page_kib'],100)
        self.assertEqual(s.create('alice','same-workload-01',{**body,'quote_id':q['quote_id']})['operation_id'],accepted['operation_id'])
        with self.assertRaises(HubError):s.create('bob','same-workload-01',{**body,'quote_id':q['quote_id']})
    def test_growth_is_only_a_distinct_supported_resource_not_a_capacity_multiplier(self):
        s=setup();cfg=configuration_profiles('T01')[1]['configuration'];s.regions_config['regions'][HOME]={'enabled':True,'verifications':{configuration_key('T01',cfg):{'passed':True,'provisioning_checks':2,'backup_restore_verified':True}}}
        r=recommend(s,'alice',request('T01'));self.assertEqual(len(r['options']),2)
        self.assertEqual(r['options'][1]['growth_components'],['data_gib']);self.assertIsNone(r['options'][1]['capacity'])
    def test_unrecognized_owner_and_policy_consent_fields_rejected(self):
        for field in ['owner_id','confirmed','verified','amount','target_url']:
            with self.assertRaises(HubError):recommend(setup(),'alice',{**request(),field:'x'})
        for tid in SAMPLES:
            r=recommend(setup(),'alice',{**request(tid),'workload':{}})
            self.assertTrue(all(o['capacity'] is None for o in r['options']));self.assertFalse(any(o['evidence_level']=='APPLICATION_VERIFIED' for o in r['options']))

class BenchmarkTests(unittest.TestCase):
    def test_fixture_rejected_by_production_even_with_verified_boolean(self):
        r=fixture_report();s=setup()
        with self.assertRaises(HubError):validate_report(s,r)
        local=validate_report(s,r,allow_fixture=True);self.assertEqual(local['metrics']['attempts'],3)
        with self.assertRaises(HubError):validate_report(s,{**r,'verified':True},allow_fixture=True)
    def test_percentiles_include_failed_attempts_and_correctness_is_counted(self):
        data=[{'elapsed_ms':n,'ok':n!=900,'correct':True,'bytes':1} for n in [10,20,900]]
        result=summarize(data,3);self.assertEqual(result['p95_ms'],'900');self.assertEqual(result['errors'],1)
        data[0]['correct']=False;self.assertEqual(summarize(data,3)['errors'],2)
    def test_every_template_requires_complete_provenance_not_a_capacity_number(self):
        for tid in SAMPLES:
            r=fixture_report(tid);self.assertIn('metrics',validate_report(setup(),r,allow_fixture=True))
            with self.assertRaises(HubError):validate_report(setup(),{**r,'generator':{}},allow_fixture=True)
        r=fixture_report();r['samples'][0]['authorization']='secret'
        with self.assertRaises(HubError):validate_report(setup(),r,allow_fixture=True)
    def test_only_admin_can_import_publish_and_retire_immutable_source(self):
        s=setup();report=fixture_report();report['execution']['mode']='AWS_ISOLATED_TEST';digest=fingerprint(report)
        s.store.rows['E#env-local-unit']={'pk':'E#env-local-unit','kind':'environment','environment_id':'env-local-unit','owner_id':'test-user','template_id':'T07','region':HOME,'configuration':configuration('T07'),'validation_run':True}
        load=lambda value:report
        for method,path,body in [('GET','/admin/benchmarks',{}),('POST','/admin/benchmarks',{'evidence_sha256':digest})]:
            with self.assertRaises(HubError):admin_route(s,method,path,body,'alice',False,load)
        imported=admin_route(s,'POST','/admin/benchmarks',{'evidence_sha256':digest},'admin',True,load);bid=imported['benchmark_id']
        self.assertEqual(imported['status'],'DRAFT');self.assertEqual(admin_route(s,'POST','/admin/benchmarks',{'evidence_sha256':digest},'admin',True,load)['benchmark_id'],bid)
        publish={'evidence_sha256':digest,'reviewed':True};admin_route(s,'POST',f'/admin/benchmarks/{bid}/publish',publish,'admin',True,load)
        args=(s,'alice','T07',HOME,configuration('T07'),SAMPLES['T07'],'a'*64,'c'*64)
        selected,excluded=matching(*args);self.assertEqual(selected[0]['evidence_level'],'SAMPLE_APPLICATION')
        for app,scenario in [('b'*64,'c'*64),('a'*64,'b'*64)]:self.assertFalse(matching(*args[:6],app,scenario)[0])
        row=s.store.rows['B#'+bid];row['measured_at']=-3000000;self.assertFalse(matching(*args)[0]);row['measured_at']=903
        admin_route(s,'POST',f'/admin/benchmarks/{bid}/retire',publish,'admin',True,load);self.assertFalse(matching(*args)[0]);self.assertEqual(len(s.store.rows['B#'+bid]['publication_history']),2)
    def test_generator_limit_cannot_be_promoted_to_proven_capacity(self):
        r=fixture_report();r['execution']['dropped_iterations']=1
        self.assertTrue(validate_report(setup(),r,allow_fixture=True)['generator_limited'])

if __name__=='__main__':unittest.main()
