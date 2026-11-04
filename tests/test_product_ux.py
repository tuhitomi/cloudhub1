"""Local risk regression. No application capacity claims or AWS mutations."""
import json,unittest
from pathlib import Path
import os
from unittest.mock import patch
from copy import deepcopy
from test_recommendations import setup,request,HOME
from cloudhub.recommendations import recommend
from cloudhub.workloads import SAMPLES,normalize
from cloudhub.recovery_actions import availability
from cloudhub.cost import Estimator
from cloudhub.errors import HubError
from cloudfront_viewer_prices import build

def book():
    value=json.loads((Path(__file__).resolve().parents[1]/'config/cloudfront-viewer-prices.review.json').read_text())
    return {key:{**row,'approved':True} for key,row in value['viewers'].items()}

class ProductUXTests(unittest.TestCase):
    def test_basic_scenarios_for_all_nine_do_not_require_hidden_advanced_fields(self):
        from cloudhub.workloads import FIELDS
        s=setup();s.estimator.rates['cloudfront_viewer_rates']=book()
        for tid in sorted(SAMPLES):
            basic={f['key']:SAMPLES[tid].get(f['key']) for f in FIELDS[tid] if not f['advanced']}
            result=recommend(s,'alice',{**request(tid),'workload':basic})
            self.assertTrue(any(o['can_select'] for o in result['options']),tid)
            self.assertTrue(all(o['capacity'] is None for o in result['options']),tid)
    def test_reviewed_global_price_overlay_preserves_regional_compute_and_closes_on_failure(self):
        from cloudhub.runtime import regional_prices
        compact={'approved':True,'price_class':'PriceClass_100','updated_at':'2026-10-19','price_version':'reviewed','units':{'cloudfront_transfer_gib':'0.085','cloudfront_requests_10000':'0.012'},'viewers':['US','APAC','EU','OTHER']}
        home={'approved':True,'units':{'ec2_hour':'0.01','cloudfront_transfer_gib':'0.085'}}
        tokyo={'approved':True,'units':{'ec2_hour':'0.02','cloudfront_transfer_gib':'0.114'}}
        documents={'/home':home,'/tokyo':tokyo,'/viewers':compact}
        with patch.dict(os.environ,{'PRICES_PARAMETER':'/home','REGIONAL_PRICES_PARAMETERS_JSON':'{"ap-northeast-1":"/tokyo"}','CLOUDFRONT_VIEWER_PRICES_PARAMETER':'/viewers'}),patch('cloudhub.runtime.load_prices',side_effect=lambda p,**kw:documents[p]):
            out=regional_prices(force=True);self.assertEqual(out['regional_rates']['ap-northeast-1']['units']['ec2_hour'],'0.02')
            self.assertEqual(out['cloudfront_viewer_rates']['APAC']['units']['cloudfront_transfer_gib'],'0.085')
            self.assertEqual(home['units']['ec2_hour'],'0.01');self.assertNotIn('cloudfront_viewer_rates',home)
            documents['/viewers']={'approved':False,'pricing_unavailable':True}
            failed=regional_prices(force=True);self.assertNotIn('cloudfront_transfer_gib',failed['units']);self.assertEqual(failed['units']['ec2_hour'],'0.01')
    def test_apac_eu_other_keep_viewer_region_and_use_explicit_actual_priceclass(self):
        s=setup();s.estimator.rates['cloudfront_viewer_rates']=book()
        for region in ['US','EU','APAC','OTHER']:
            r=recommend(s,'alice',{**request('T02'),'workload':{**SAMPLES['T02'],'viewer_geography':region}});option=r['options'][0]
            self.assertTrue(option['can_select']);self.assertEqual(r['workload']['viewer_geography'],region)
            self.assertEqual(option['cost']['assumptions']['cloudfront_price_class'],'PriceClass_100')
            self.assertEqual(option['cost']['assumptions']['viewer_charged_groups'],['US','CA','EU'])
            self.assertEqual(option['cost']['units']['cloudfront_requests_10000'],'0.0120000000')
            self.assertIsNone(option['capacity'])
    def test_missing_viewer_price_has_partial_subtotal_without_us_substitute(self):
        r=recommend(setup(),'alice',{**request('T02'),'workload':{**SAMPLES['T02'],'viewer_geography':'APAC'}})
        cost=r['options'][0]['cost'];self.assertIsNone(cost['total_milliusd']);self.assertGreater(cost['known_subtotal_milliusd'],0)
        self.assertNotIn('transfer',cost['lines']);self.assertNotIn('cloudfront_requests',cost['lines'])
        self.assertEqual(r['options'][0]['selection_blockers'],['PRICE_INCOMPLETE'])
    def test_missing_core_rate_is_null_and_known_cost_is_retained(self):
        s=setup();del s.estimator.rates['units']['ec2_hour'];cost=s.estimator.estimate('T01',1)
        self.assertFalse(cost['approved']);self.assertIsNone(cost['lines']['compute']);self.assertIsNone(cost['total_milliusd'])
        self.assertGreater(cost['known_subtotal_milliusd'],0);self.assertIn('price:ec2_hour',cost['missing_components'])
    def test_t03_basic_inputs_do_not_require_cpu_ram_or_hidden_cost_parameters(self):
        w={k:v for k,v in SAMPLES['T03'].items() if k in ['active_users','actions_per_minute','query_complexity','data_mib']}
        r=recommend(setup(),'alice',{**request('T03'),'workload':w});option=r['options'][0]
        self.assertTrue(option['can_select']);self.assertIsNone(r['workload']['min_cpu_millicores']);self.assertIsNone(r['workload']['min_memory_mib'])
        self.assertEqual(r['input_assumptions']['api_calls_per_action'],1);self.assertEqual(r['input_assumptions']['background_rps'],0)
        self.assertIsNone(option['capacity']);self.assertEqual(option['creation_defaults']['planning_workload'],r['workload'])
    def test_advice_and_quote_share_policy_workload_prices_horizon_and_exact_total(self):
        s=setup();s.estimator.rates['cloudfront_viewer_rates']=book();payload={**request('T02'),'estimate_hours':4,'workload':{**SAMPLES['T02'],'viewer_geography':'APAC'}}
        o=recommend(s,'alice',payload)['options'][0];body={k:v for k,v in o['creation_defaults'].items() if k!='profile_id'}
        body['operating_policy']={**body['operating_policy'],'confirmed':True};body['planning_workload']=body.pop('planning_workload')
        quote=s.create_estimate('alice',body)
        self.assertEqual(quote['preview']['total_usd'],o['cost']['total_usd']);self.assertEqual(quote['first_period']['total_usd'],o['first_period']['total_usd'])
        self.assertEqual(quote['planning_workload']['viewer_geography'],'APAC');self.assertEqual(quote['estimate_hours'],4)
        s.estimator.rates['cloudfront_viewer_rates']['APAC']['units']['cloudfront_requests_10000']='0.02'
        with self.assertRaises(HubError) as caught:s.create('alice','changed-prices-01',{**body,'quote_id':quote['quote_id']})
        self.assertEqual(caught.exception.code,'QUOTE_CHANGED')
    def test_budget_and_resource_limits_are_distinct(self):
        r=recommend(setup(),'alice',request(budget_milliusd=0));self.assertEqual(r['options'][0]['selection_blockers'],['BUDGET_EXCEEDED'])
        r=recommend(setup(),'alice',{**request(),'workload':{**SAMPLES['T07'],'data_kib':999999,'file_count':999999}})
        self.assertFalse(r['options']);self.assertEqual(r['excluded'][0]['code'],'RESOURCE_NOT_FIT')
    def test_recovery_hints_distinguish_deleted_expired_busy_protected_and_ready(self):
        s=setup();base={'template_id':'T07','region':HOME,'status':'AVAILABLE','retain_until':s.clock()+60}
        self.assertTrue(availability(s,base)['restore']['allowed'])
        for patch,reason in [({'status':'DELETED'},'DELETED'),({'status':'DELETE_FAILED'},'DELETE_FAILED'),({'status':'PENDING'},'PENDING'),({'retain_until':s.clock()-1},'EXPIRED'),({'restore_lock':'op-123'},'BUSY')]:
            got=availability(s,{**base,**patch});self.assertFalse(got['restore']['allowed']);self.assertEqual(got['restore']['reason'],reason)
        failed=availability(s,{**base,'status':'DELETE_FAILED'});self.assertFalse(failed['export']['allowed']);self.assertEqual(failed['export']['reason'],'DELETE_FAILED');self.assertTrue(failed['delete']['allowed'])
        got=availability(s,{**base,'retirement_lock':'op-123'});self.assertFalse(got['delete']['allowed']);self.assertEqual(got['delete']['reason'],'PROTECTED');self.assertTrue(got['export']['allowed'])
    def test_collector_does_not_accept_global_free_tier_as_regional_price(self):
        with self.assertRaises(ValueError):build([{'TermType':'OnDemand','Currency':'USD','StartingRange':'0','usageType':'Global-DataTransfer-Out-Bytes','EndingRange':'1024','PricePerUnit':'0'}],'v','date')

if __name__=='__main__':unittest.main()
