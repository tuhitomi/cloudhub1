"""LOCAL only: bounded generator correctness and publication safety."""
import io,json,hashlib,unittest
from copy import deepcopy
from unittest.mock import patch
from cloudhub import benchmark_agent as agent
from cloudhub.benchmarks import validate_report,load_evidence
from cloudhub.errors import HubError
from cloudhub.catalog import configuration
from test_recommendations import setup,fixture_report,request
from cloudhub.recommendations import recommend

class BenchmarkToolTests(unittest.TestCase):
    def test_actual_lambda_and_api_limits_are_separate_from_forecast_or_unknown_quotas(self):
        from benchmark_workloads import quota_snapshot
        class Client:
            def get_account_settings(self):return {'AccountLimit':{'ConcurrentExecutions':10}}
            def get_function_concurrency(self,**kw):return {}
            def get_stages(self,**kw):return {'Items':[{'StageName':'$default','DefaultRouteSettings':{'ThrottlingRateLimit':5}}]}
        class Session:
            def __init__(self):self.regions=[]
            def client(self,name,region_name):self.regions.append(region_name);return Client()
        session=Session();value=quota_snapshot(session,[{'id':'test','type':'AWS::Lambda::Function'},{'id':'api','type':'AWS::ApiGatewayV2::Api'}],'ap-northeast-1',{}, {'cap_milliusd':120000})
        self.assertEqual(value['provider']['lambda_account']['ConcurrentExecutions'],10);self.assertIsNone(value['other_account_capacity_quotas']);self.assertTrue(all(r=='ap-northeast-1' for r in session.regions))

    def test_cloudfront_cache_state_requires_observed_headers_not_an_assumption(self):
        self.assertEqual(agent.classify_cache([]),'UNKNOWN');self.assertEqual(agent.classify_cache([{'x_cache':None}]),'UNKNOWN')
        hit={'x_cache':'Hit from cloudfront'};miss={'x_cache':'Miss from cloudfront'}
        self.assertEqual(agent.classify_cache([hit]),'WARM');self.assertEqual(agent.classify_cache([miss]),'COLD');self.assertEqual(agent.classify_cache([hit,miss]),'MIXED')
        r=fixture_report('T02');r['execution']['mode']='AWS_ISOLATED_TEST';r['observations']['cache_state']='MIXED';r['observations']['cache_observations']=[hit]
        with self.assertRaises(HubError):validate_report(setup(),r)

    def test_generator_bounds_and_invalid_remote_scope_cannot_execute(self):
        for args in [(0,1,1),(1,101,1),(1,1,17),(3600,100,1)]:
            with self.assertRaises(ValueError):agent.bounded_arrival(lambda:None,*args)
        for nonce,index,action in [('bad',0,'read'),('a'*24,2,'read'),('a'*24,0,'delete-all')]:
            with self.assertRaises(ValueError):agent.remote_marker_script(nonce,index,action)
        self.assertEqual(len(agent.revision()),64)

    def test_s3_single_conditional_put_checksum_and_exact_version_cleanup(self):
        class S3:
            def put_object(self,**kw):self.put=kw;return {'VersionId':'owned-version'}
            def get_object(self,**kw):self.get=kw;return {'Body':io.BytesIO(self.put['Body'])}
            def delete_object(self,**kw):self.deleted=kw
        s3=S3();probe,cleanup,scope=agent.s3_probe(s3,'owned-bucket','123456789012','a'*24,8192)
        self.assertEqual(len(s3.put['Body']),8192);self.assertEqual(s3.put['IfNoneMatch'],'*');self.assertTrue(probe()['correct']);cleanup()
        self.assertEqual(s3.deleted['Key'],s3.put['Key']);self.assertEqual(s3.deleted['VersionId'],'owned-version')
        self.assertEqual(scope['bytes'],8192)

    def test_fractional_target_accepted_without_accepting_nan_or_boolean(self):
        for rate in ['NaN','Infinity','0',True]:
            r=fixture_report();r['execution']['target_rate']=rate
            with self.assertRaises(HubError):validate_report(setup(),r,allow_fixture=True)
        r=fixture_report();r['execution']['target_rate']='0.5'
        self.assertFalse(validate_report(setup(),r,allow_fixture=True)['generator_limited'])

    def test_empty_provider_metrics_and_unobserved_scale_out_are_not_proof(self):
        for tid in ['T01','T03','T04','T05','T08']:
            r=fixture_report(tid);r['execution']['mode']='AWS_ISOLATED_TEST';r['observations']['cpu_credits_before']={};r['observations']['cpu_credits_after']={}
            with self.assertRaises(HubError):validate_report(setup(),r)

    def test_raw_source_and_report_must_match_and_sensitive_raw_is_rejected(self):
        report=fixture_report();report['evidence_files']=[{'name':'raw-observations.json','sha256':'0'*64}]
        class S3:
            def __init__(self,values):self.values=iter(values)
            def get_object(self,**kw):
                blob=next(self.values);return {'ContentLength':len(blob),'Body':io.BytesIO(blob)}
        for raw in [[{'unexpected':1}],{'authorization':'do-not-publish'}]:
            source=json.dumps(raw).encode();report['evidence_files'][0]['sha256']=hashlib.sha256(source).hexdigest();blob=json.dumps(report).encode();digest=hashlib.sha256(blob).hexdigest()
            with patch.dict('os.environ',{'BENCHMARK_BUCKET':'private'}),patch('boto3.client',return_value=S3([blob,source])):
                with self.assertRaises(HubError):load_evidence(digest)

    def test_resource_unknowns_do_not_become_zero_and_renewal_cap_is_respected(self):
        s=setup();r=recommend(s,'alice',{**request('T01'),'operating_policy':{'mode':'AUTO_RENEW','period_minutes':60,'ending_policy':'BACKUP_RETIRE','budget_limit_milliusd':1}})
        self.assertFalse(r['options'][0]['can_select']);self.assertEqual(r['options'][0]['policy_budget_status'],'EXCEEDED')
        r=recommend(s,'alice',{**request('T01'),'workload':{}})
        self.assertIsNone(r['options'][0]['capacity']);self.assertEqual(r['options'][0]['resource_assessment']['status'],'NEEDS_INFORMATION')

    def test_efs_backup_and_restore_envelope_grows_with_declared_data(self):
        from cloudhub.workloads import SAMPLES
        s=setup();small=recommend(s,'alice',request('T08'))['options'][0]
        large=recommend(s,'alice',{**request('T08'),'workload':{**SAMPLES['T08'],'data_mib':10240}})['options'][0]
        self.assertGreater(large['first_period']['total_milliusd'],small['first_period']['total_milliusd'])
        self.assertGreater(large['after_shutdown']['total_milliusd'],small['after_shutdown']['total_milliusd'])

if __name__=='__main__':unittest.main()
