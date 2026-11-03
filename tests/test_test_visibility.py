"""Local only: hide presentation, preserve accounting and dangerous-state visibility."""
import sys,unittest
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch,Mock
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'));sys.path.insert(0,str(ROOT/'scripts'))
from cloudhub.test_visibility import environments,include_tests,hidden_account,marked
from cloudhub.store import MemoryStore
from cloudhub.errors import HubError
from archive_test_data import plan,archive,commit_legacy_profile
from cloudhub.portal_api import route
MARK={'schema':1,'classification':'TEST','hidden_by_default':True}
def env(**values):return {'pk':'E#env-one','kind':'environment','environment_id':'env-one','owner_id':'test-owner',
    'status':'DELETED','quota_released':True,'validation_run':True,'cleanup_report':{'checked_at':100,'residual':[],'unknown':[]},**values}
class TestVisibility(unittest.TestCase):
    def test_unmarked_human_records_never_inferred_from_names(self):
        row=env(name='test demo');self.assertEqual(len(environments([row],{},dict)['items']),1)
        self.assertFalse(marked({'test_data':True}));self.assertFalse(marked({'test_data':{'schema':1,'classification':'TEST'}}))
    def test_hidden_only_when_safe_and_explicit(self):
        row=env(test_data=MARK);self.assertEqual(environments([row],{},dict)['hidden_test_count'],1)
        for delta in [{'status':'READY'},{'needs_admin':True},{'lock':'op-live'},{'cost_lock':'op-cost'},{'quota_released':False},
                      {'cleanup_report':{}},{'cleanup_report':{'checked_at':1,'residual':[{}]}},{'cleanup_report':{'checked_at':1,'unknown':[{}]}}]:
            with self.subTest(delta=delta):self.assertEqual(len(environments([{**row,**delta}],{},dict)['items']),1)
    def test_show_again_and_retained_report_warning_without_clean_claim(self):
        row=env(test_data=MARK,cleanup_report={'checked_at':1,'retained':[{'id':'old-copy'}],'billable':[{}]})
        value=environments([row],{},dict);self.assertEqual(value['retained_test_report_count'],1)
        value=environments([row],{'include_test':'true'},dict);self.assertEqual(value['items'],[row]);self.assertEqual(value['hidden_test_count'],0)
        self.assertEqual(row['cleanup_report']['retained'],[{'id':'old-copy'}])
    def test_query_is_strict_and_accounts_must_be_disabled_in_both_sources(self):
        with self.assertRaises(HubError):include_tests({'include_test':'yes'})
        p={'enabled':False,'test_data':MARK}
        self.assertTrue(hidden_account({'enabled':False},p));self.assertFalse(hidden_account({'enabled':True},p))
        self.assertFalse(hidden_account({'enabled':False},{**p,'enabled':True}))
    def test_preview_keeps_real_accounts_and_ambiguous_environments(self):
        users=[{'owner_id':'test-owner','email':'cloudhub08-fixture@example.invalid','enabled':False},
               {'owner_id':'human','email':'human@example.test','enabled':False},
               {'owner_id':'enabled','email':'cloudhub-x@example.invalid','enabled':True}]
        rows=[env(),env(pk='E#real',owner_id='human',validation_run=False)]
        result=plan(rows,users);self.assertEqual({v['pk'] for v in result['items']},{'U#test-owner','E#env-one'})
    def test_archive_is_replay_safe_and_does_not_touch_finance_or_backup(self):
        store=MemoryStore();row=env();store.rows[row['pk']]=row
        for k in ['Q#GLOBAL','Q#test-owner','F#reservation','J#history','R#backup']:store.rows[k]={'pk':k,'sentinel':13}
        before=deepcopy(store.rows);item=plan([row],[])['items'][0]
        self.assertEqual(archive(store,item,100),'ARCHIVED');self.assertEqual(archive(store,item,101),'ALREADY_ARCHIVED')
        for k,v in before.items():
            if k!='E#env-one':self.assertEqual(store.rows[k],v)
        self.assertEqual(len([r for r in store.rows.values() if r.get('kind')=='test_visibility_audit']),1)
        self.assertEqual(store.rows['E#env-one']['status'],'DELETED')
    def test_change_to_active_before_archive_is_refused(self):
        store=MemoryStore();row=env();item=plan([row],[])['items'][0];store.rows[row['pk']]={**row,'status':'READY'}
        self.assertEqual(archive(store,item,100),'STATE_CHANGED_REVIEW_REQUIRED');self.assertNotIn('test_data',store.rows[row['pk']])
    def test_account_archive_requires_live_provider_proof_and_refuses_enabled_users(self):
        store=MemoryStore();user={'owner_id':'test-owner','email':'cloudhub-safe@example.invalid','enabled':False}
        item=plan([], [user])['items'][0]
        with self.assertRaises(ValueError):archive(store,item,100)
        accounts=Mock();accounts.find.return_value={**user,'enabled':True}
        self.assertEqual(archive(store,item,100,accounts),'PROVIDER_STATE_CHANGED_REVIEW_REQUIRED');self.assertEqual(store.rows,{})
        accounts.find.return_value=user
        store.rows[item['pk']]={'pk':item['pk'],'owner_id':'test-owner','enabled':True}
        self.assertEqual(archive(store,item,100,accounts),'ARCHIVED');self.assertFalse(store.get(item['pk'])['enabled'])
    def test_legacy_missing_owner_requires_exact_subject_key_and_current_provider_proof(self):
        store=MemoryStore();user={'owner_id':'test-owner','email':'cloudhub-safe@example.invalid','enabled':False}
        item=plan([], [user])['items'][0];accounts=Mock();accounts.find.return_value=user
        store.rows[item['pk']]={'pk':item['pk'],'enabled':False,'purpose':'old synthetic fixture'}
        self.assertEqual(archive(store,item,100,accounts),'ARCHIVED');self.assertEqual(store.get(item['pk'])['owner_id'],'test-owner')
        with self.assertRaises(ValueError):archive(store,{**item,'pk':'U#someone-else'},100,accounts)
    def test_native_legacy_update_is_conditional_preserves_unknown_fields_and_writes_audit_atomically(self):
        from cloudhub.store import DynamoStore
        client=Mock();store=DynamoStore('table',client)
        before={'pk':'U#test-owner','enabled':False,'purpose':'fixture'}
        commit_legacy_profile(store,{**before,'owner_id':'test-owner','test_data':MARK},
            {'pk':'M#audit','kind':'test_visibility_audit'},before)
        actions=client.transact_write_items.call_args.kwargs['TransactItems']
        self.assertEqual(len(actions),2);self.assertIn('Update',actions[0]);self.assertIn('Put',actions[1])
        update=actions[0]['Update'];self.assertIn('attribute_exists(pk)',update['ConditionExpression'])
        self.assertIn('attribute_not_exists(#version)',update['ConditionExpression']);self.assertNotIn('REMOVE',update['UpdateExpression'])
        self.assertEqual(actions[1]['Put']['Item']['version'],{'N':'1'})
    def test_admin_lists_revalidate_and_keep_cursor_when_filtered(self):
        service=Mock();service.store.get.return_value={'test_data':MARK,'enabled':False}
        accounts=Mock();accounts.assert_admin=Mock();accounts.list.return_value={'items':[{'owner_id':'test-owner','enabled':False}],'next_cursor':'next-page'}
        with patch('cloudhub.accounts.Accounts',return_value=accounts),patch.dict('os.environ',{'USER_POOL_ID':'pool'}):
            with self.assertRaises(HubError):route(service,'GET','/admin/users',{},None,'human',False,{}, {},dict)
            result,status=route(service,'GET','/admin/users',{},None,'admin',True,{'username':'admin'}, {},dict)
        self.assertEqual(status,200);self.assertEqual(result['items'],[]);self.assertEqual(result['next_cursor'],'next-page')
        self.assertEqual(result['hidden_test_count'],1);accounts.assert_admin.assert_called_once_with('admin','admin')
