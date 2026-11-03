import sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from copy import deepcopy
from botocore.exceptions import ClientError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from cloudhub.admin_directory import users,environment_owners,search_term
from cloudhub.errors import HubError
from cloudhub.portal_api import route
OWNER='11111111-1111-1111-1111-111111111111'
def user(owner=OWNER,email='Member@sample.test',**kw):return {'owner_id':owner,'email':email,'username':'login-'+owner,'enabled':True,**kw}
def service():
    s=Mock();s.store.get.return_value=None;s.limits.return_value={'wallet':{'balance_milliusd':10000}};return s
class AdminDirectoryTests(unittest.TestCase):
    def test_search_matches_later_pages_case_insensitively_without_provider_filter_injection(self):
        a=Mock();a.list.side_effect=[{'items':[user(email='other@sample.test')],'next_cursor':'later'}, {'items':[user(email='Member@sample.test')],'next_cursor':None}]
        value=users(service(),a,{'q':'  MEMBER@SAMPLE  '});self.assertEqual(len(value['items']),1);self.assertTrue(value['search_complete'])
        self.assertEqual(value['directory_pages_scanned'],2);self.assertEqual(a.list.call_args_list[1].args,('later',))
    def test_search_budget_is_bounded_and_continuation_is_honest(self):
        a=Mock();a.list.return_value={'items':[],'next_cursor':'more'}
        value=users(service(),a,{'q':'absent'});self.assertEqual(a.list.call_count,3)
        self.assertFalse(value['search_complete']);self.assertEqual(value['next_cursor'],'more')
    def test_id_search_and_test_visibility_remain_separate(self):
        s=service();s.store.get.return_value={'enabled':False,'test_data':{'schema':1,'classification':'TEST','hidden_by_default':True}}
        a=Mock();a.list.return_value={'items':[user(enabled=False)],'next_cursor':None}
        self.assertEqual(users(s,a,{'q':OWNER})['items'],[])
        self.assertEqual(len(users(s,a,{'q':OWNER,'include_test':'true'})['items']),1)
    def test_invalid_queries_rejected_before_provider_calls(self):
        for q in ['a'*129,'bad\nquery',[],None]:
            with self.subTest(q=q),self.assertRaises(HubError):search_term({'q':q})
        a=Mock();a.list.return_value={'items':[user()],'next_cursor':None}
        self.assertEqual(users(service(),a,{'q':'" OR email=*'})['items'],[])
        a.list.assert_called_once_with(None)
    def test_owner_email_joins_by_subject_only_and_does_not_mutate_source(self):
        raw={'items':[{'environment_id':'env-a','owner_id':OWNER},{'environment_id':'env-b','owner_id':'legacy-validation-run'}],'hidden_test_count':175};before=deepcopy(raw)
        a=Mock();a.list.return_value={'items':[user(),user('22222222-2222-2222-2222-222222222222','not-owner@sample.test')],'next_cursor':None}
        value=environment_owners(raw,a,100)
        self.assertEqual(value['items'][0]['owner_email'],'Member@sample.test');self.assertEqual(value['items'][1]['owner_email'],None)
        self.assertEqual(value['items'][1]['owner_email_status'],'LEGACY_ID');self.assertEqual(raw,before)
    def test_directory_outage_is_unknown_email_not_fabricated_or_failed_environment_list(self):
        a=Mock();a.list.side_effect=ClientError({'Error':{'Code':'TooManyRequestsException'}},'ListUsers')
        value=environment_owners({'items':[{'owner_id':OWNER}]},a,100)
        self.assertIsNone(value['items'][0]['owner_email']);self.assertEqual(value['items'][0]['owner_email_status'],'UNAVAILABLE')
    def test_admin_permission_revalidated_before_contacts_or_search(self):
        s=service();a=Mock();a.assert_admin=Mock()
        with patch('cloudhub.accounts.Accounts',return_value=a),patch.dict('os.environ',{'USER_POOL_ID':'pool'}):
            for path in ['/admin/users','/admin/environments']:
                with self.assertRaises(HubError):route(s,'GET',path,{},None,OWNER,False,{}, {},dict)
        a.list.assert_not_called();a.assert_admin.assert_not_called()
