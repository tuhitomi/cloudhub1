"""Local failure/consistency tests for Standard-parameter regional proof shards."""
import json,os,sys,unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from cloudhub.runtime import region_configuration
from cloudhub.catalog import ACTIVE_TEMPLATES,configuration_profiles,configuration_key

HOME='ap-southeast-1'; TARGET='ap-northeast-1'
PATH='/cloudhub/cloudhub-pages-live/regions/verifications/'+TARGET

class ParameterReadTests(unittest.TestCase):
    def test_client_reused_but_force_reads_fresh_and_failure_closes_prices(self):
        from cloudhub import runtime
        sdk=Mock()
        sdk.get_parameter.side_effect=[{'Parameter':{'Value':'{"approved":true,"version":1}'}},
            {'Parameter':{'Value':'{"approved":true,"version":2}'}},RuntimeError('offline')]
        with patch.object(runtime,'_PARAMETER_CLIENT',None),patch.object(runtime,'_PRICE_CACHE',{}),patch('boto3.client',return_value=sdk) as factory:
            self.assertEqual(runtime.load_prices('/prices')['version'],1)
            self.assertEqual(runtime.load_prices('/prices')['version'],1)
            self.assertEqual(runtime.load_prices('/prices',force=True)['version'],2)
            failed=runtime.load_prices('/prices',force=True)
            self.assertFalse(failed['approved']);self.assertTrue(failed['pricing_unavailable'])
            self.assertEqual(sdk.get_parameter.call_count,3);factory.assert_called_once()

class ShardTests(unittest.TestCase):
    def root(self,path=PATH):
        return {'control_region':HOME,'regions':{HOME:{'enabled':True},TARGET:{'prepared':True,'enabled':True,'verifications_parameter':path,'verifications':{'stale':{'passed':True}}}}}
    def run_config(self,root,shard):
        with patch.dict(os.environ,{'AWS_REGION':HOME}),patch('cloudhub.runtime.configuration_document',return_value=root),patch('cloudhub.runtime.load_prices',return_value=shard) as loader:
            return region_configuration(),loader
    def test_all_catalog_proof_shapes_fit_one_standard_parameter_without_mutating_root(self):
        proofs={configuration_key(t,p['configuration']):{'passed':True,'region':TARGET,'provisioning_checks':2,'backup_restore_verified':True} for t in ACTIVE_TEMPLATES for p in configuration_profiles(t)}
        shard={'schema':1,'region':TARGET,'verifications':proofs}
        self.assertEqual(len(proofs),24);self.assertLessEqual(len(json.dumps(shard,separators=(',',':')).encode()),4096)
        root=self.root();before=deepcopy(root);result,loader=self.run_config(root,shard)
        self.assertEqual(len(result['regions'][TARGET]['verifications']),24);self.assertTrue(result['regions'][HOME]['enabled'])
        self.assertEqual(root,before);loader.assert_called_once_with(PATH)
    def test_unavailable_or_wrong_region_shard_never_uses_stale_proof(self):
        for shard in [{'pricing_unavailable':True,'schema':1,'region':TARGET,'verifications':{'stale':{}}},{'schema':1,'region':HOME,'verifications':{}},{'region':TARGET,'verifications':{}},{'schema':1,'region':TARGET,'verifications':[]}]:
            with self.subTest(shard=shard):
                result,_=self.run_config(self.root(),shard)
                self.assertFalse(result['regions'][TARGET]['enabled']);self.assertEqual(result['regions'][TARGET]['verifications'],{})
                self.assertTrue(result['regions'][HOME]['enabled'])
    def test_parameter_path_cannot_escape_region_or_application_namespace(self):
        for path in ['/unrelated/secret','/cloudhub/cloudhub-pages-live/regions/verifications/'+HOME,{'path':PATH}]:
            with self.subTest(path=path):
                result,loader=self.run_config(self.root(path),{})
                self.assertFalse(result['regions'][TARGET]['enabled']);loader.assert_not_called()
    def test_inline_t07_configuration_remains_compatible(self):
        root={'control_region':HOME,'regions':{TARGET:{'enabled':True,'verifications':{'key':{'passed':True}}}}}
        result,loader=self.run_config(root,{})
        self.assertEqual(result,root);loader.assert_not_called()

if __name__=='__main__':unittest.main()
