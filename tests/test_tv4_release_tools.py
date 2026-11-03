"""Release metadata must reject stale/unsafe sources and distinguish fixture evidence."""
import hashlib,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from prepare_product_release import prepare
from check_tv4 import run
import prepare_product_0_8_packet as packet

class ReleaseReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='cloudhub-release-unit-')
        self.root=Path(self.temp.name).resolve()
        self.assertTrue(self.root.is_relative_to(Path(tempfile.gettempdir()).resolve()))
        (self.root/'team').mkdir();(self.root/'backend').mkdir()
        (self.root/'backend/example.py').write_text('value = 1\n',encoding='utf-8')
        (self.root/'package.json').write_text('{"version":"0.8.0"}',encoding='utf-8')
        self.rows=[{'path':'backend/example.py','owner':'TV4'},{'path':'backend/missing.py','owner':'TV2'}]
        (self.root/'team/file-ownership.json').write_text(json.dumps({'files':self.rows}),encoding='utf-8')
        self.results={'scope':'LOCAL_SUPPORT_FIXTURE','passed':True,'tests_run':1,'recorded_at':'2026-11-04T00:00:00Z',
                      'covered_files':{'backend/example.py':hashlib.sha256((self.root/'backend/example.py').read_bytes()).hexdigest()}}
    def tearDown(self):self.temp.cleanup()
    def test_fixture_pass_and_missing_sources_never_approve_native_review(self):
        value=prepare(self.results,self.root)
        self.assertFalse(value['ready_for_native_review']);self.assertFalse(value['aws_deployed'])
        self.assertEqual(value['missing_source_files'],['backend/missing.py']);self.assertEqual(value['tests']['scope'],'LOCAL_SUPPORT_FIXTURE')
    def test_stale_results_reject_source_change(self):
        (self.root/'backend/example.py').write_text('value = 2\n',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'source drift'):prepare(self.results,self.root)
    def test_unsafe_covered_path_never_reads_outside_the_source(self):
        self.results['covered_files']={'../outside':'0'*64}
        with self.assertRaisesRegex(ValueError,'Unsafe source path'):prepare(self.results,self.root)
    def test_failed_or_unscoped_results_cannot_be_relabelled_as_pass(self):
        for change in ({'passed':False},{'scope':'AWS_REAL'},{'tests_run':0},{'covered_files':{}}):
            with self.subTest(change=change),self.assertRaises(ValueError):prepare({**self.results,**change},self.root)
    def test_snapshot_is_reproducible_for_the_same_sources(self):
        first=prepare(self.results,self.root);second=prepare(self.results,self.root)
        self.assertEqual(first['source_snapshot_sha256'],second['source_snapshot_sha256']);self.assertEqual(first['files'],second['files'])
    def test_source_fingerprint_survives_git_crlf_to_lf_normalization(self):
        self.results['fingerprint_format']='UTF8_LF_SHA256'
        self.results['covered_files']['backend/example.py']=hashlib.sha256(b'value = 1\n').hexdigest()
        first=prepare(self.results,self.root)
        (self.root/'backend/example.py').write_bytes(b'value = 1\r\n')
        second=prepare(self.results,self.root)
        self.assertEqual(first['files'],second['files']);self.assertEqual(first['source_snapshot_sha256'],second['source_snapshot_sha256'])
    def test_missing_repository_modules_report_blocked_without_running_tests(self):
        result=run(root=self.root)
        self.assertFalse(result['passed']);self.assertEqual(result['status'],'BLOCKED_MISSING_DEPENDENCIES')
        self.assertEqual(result['scope'],'LOCAL_REPOSITORY');self.assertEqual(result['tests_run'],0)
    def test_private_configuration_is_rejected(self):
        self.rows.append({'path':'config/settings.live.json','owner':'TV4'});(self.root/'config').mkdir()
        (self.root/'config/settings.live.json').write_text('{}',encoding='utf-8')
        (self.root/'team/file-ownership.json').write_text(json.dumps({'files':self.rows}),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Private/live'):prepare(self.results,self.root)
    def test_partial_manifest_cannot_reach_packaging_or_target_credentials(self):
        manifest=self.root/'manifest.json';manifest.write_text(json.dumps({'ready_for_native_review':False,'tests':{'passed':True}}),encoding='utf-8')
        missing=self.root/'missing';out=self.root/'artifacts'
        argv=['packet','--manifest',str(manifest),'--public-config',str(missing),'--deps',str(missing),
              '--out-dir',str(out),'--deployment-target',str(missing)]
        with patch.object(sys,'argv',argv),self.assertRaisesRegex(ValueError,'Complete repository sources'):
            packet.main()
        self.assertFalse(out.exists())

if __name__=='__main__':unittest.main()
