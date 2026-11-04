"""LOCAL only: public projection cannot write data or authorize creation."""
import sys,json,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from test_regions import setup
from cloudhub import api
from cloudhub.public_catalog import read
from cloudhub.errors import HubError
from cloudhub.registration import set_defaults

class PublicCatalogTests(unittest.TestCase):
 def test_public_projection_has_nine_templates_and_no_account_or_resource_identifiers(self):
  service=setup();service.store.rows['U#private']={'owner_id':'private','email':'private@example.com'}
  before=json.dumps(service.store.rows,sort_keys=True)
  result=read(service)
  self.assertEqual([r['template_id'] for r in result['items']],[f'T0{i}' for i in range(1,10)])
  self.assertNotIn('private',json.dumps(result));self.assertNotIn('arn:',json.dumps(result))
  self.assertEqual(before,json.dumps(service.store.rows,sort_keys=True))
  self.assertFalse(result['signup_policy']['aws_credit_grant'])
 def test_defaults_follow_admin_policy_without_exposing_global_reservations(self):
  service=setup();set_defaults(service,'admin',{'max_active':1,'budget_milliusd':3000})
  result=read(service)['signup_policy'];self.assertEqual(result['max_active'],1);self.assertEqual(result['budget_milliusd'],3000)
  self.assertNotIn('reserved_milliusd',result);self.assertNotIn('updated_by',result)
 def test_preview_uses_selected_regional_prices_and_never_issues_quote_or_reservation(self):
  service=setup();before=json.dumps(service.store.rows)
  body={'template_id':'T07','region':'ap-northeast-1','profile_id':'standard','hours':'4'}
  preview=read(service,body)['preview'];self.assertEqual(preview['region'],'ap-northeast-1')
  self.assertEqual(preview['estimate']['region'],preview['region']);self.assertEqual(preview['hours'],4)
  self.assertFalse(preview['is_quote']);self.assertEqual(before,json.dumps(service.store.rows))
  self.assertEqual(preview['estimate']['total_milliusd'],service.estimator_for('ap-northeast-1').estimate('T07',4)['total_milliusd'])
 def test_unknown_price_is_not_displayed_as_zero_and_unverified_configuration_stays_closed(self):
  preview=read(setup(),{'template_id':'T07','region':'us-east-1','profile_id':'files'})['preview']
  self.assertIsNone(preview['estimate']['total_milliusd']);self.assertFalse(preview['create_enabled'])
 def test_query_cannot_select_owner_arbitrary_configuration_or_local_zone(self):
  for patch_body in [{'owner_id':'other'},{'template_id':'T10','region':'ap-southeast-1','profile_id':'standard'},
   {'template_id':'T07','region':'us-east-1-bos-1a','profile_id':'standard'},
   {'template_id':'T07','region':'ap-southeast-1','profile_id':'giant'},
   {'template_id':'T07','region':'ap-southeast-1','profile_id':'standard','hours':'999'}]:
   with self.subTest(patch_body=patch_body),self.assertRaises(HubError):read(setup(),patch_body)
 def test_only_get_public_catalog_bypasses_identity_and_account_routes_remain_protected(self):
  with patch.object(api,'SERVICE',setup()):
   for path,method,status in [('/public/catalog','GET',200),('/public/catalog','POST',401),('/templates','GET',401),('/environments','GET',401),('/admin/signup-defaults','GET',401)]:
    response=api.handler({'rawPath':path,'requestContext':{'http':{'method':method}}})
    self.assertEqual(response['statusCode'],status,(path,method))
 def test_infra_public_exception_is_specific_and_does_not_change_default_jwt(self):
  sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
  from generate_infra import build_template
  resources=build_template()['Resources'];props=resources['ApiFunction']['Properties']['Events']['PublicCatalog']['Properties']
  self.assertEqual(props['Auth'],{'Authorizer':'NONE'});self.assertEqual(props['Path'],'/public/catalog')
  self.assertTrue(resources['HttpApi']['Properties']['Auth']['DefaultAuthorizer'])
