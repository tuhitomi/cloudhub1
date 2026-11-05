"""Observer assertions use a local HTTP double; no CDN or AWS claim."""
import sys,hashlib
from pathlib import Path
from unittest import TestCase
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from check_t02_publication import observe

class ObserverTests(TestCase):
    def setUp(self):
        self.rid='release-'+'a'*24
        self.a={'release_id':'initial','files':[{'key':'app.js','size':1,'sha256':hashlib.sha256(b'A').hexdigest()}]}
        self.b={'release_id':self.rid,'files':[{'key':'app.js','size':1,'sha256':hashlib.sha256(b'B').hexdigest()}]}
    def fetch(self,path,limit):
        if path=='/':return 302,{'location':'/_cloudhub_site/'+self.rid+'/index.html','cache-control':'no-store'},b''
        if path=='/_cloudhub_site/initial/app.js':return 200,{'x-cache':'Hit from cloudfront'},b'A'
        if path=='/_cloudhub_site/'+self.rid+'/app.js':return 200,{'x-cache':'Hit from cloudfront'},b'B'
        return 403,{},b''
    def test_warm_b_and_old_a_are_verified_separately(self):
        r=observe('https://dexample.cloudfront.net',self.b,self.a,2,self.fetch)
        self.assertTrue(r['passed']);self.assertEqual(8,len(r['checks']))
    def test_wrong_cached_bytes_fail_even_with_http_200(self):
        def wrong(path,limit):
            status,h,data=self.fetch(path,limit)
            return status,h,b'A' if path.endswith(self.rid+'/app.js') else data
        self.assertFalse(observe('https://dexample.cloudfront.net',self.b,self.a,2,wrong)['passed'])
    def test_internal_path_in_manifest_is_rejected(self):
        self.b['files'][0]['key']='.cloudhub/secret.txt'
        with self.assertRaises(ValueError):observe('https://dexample.cloudfront.net',self.b,None,2,self.fetch)
