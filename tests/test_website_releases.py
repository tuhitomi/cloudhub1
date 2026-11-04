"""Local content-switch and rollback tests; CloudFront calls are doubles."""
from copy import deepcopy
from unittest import TestCase
import test_direct_uploads as fixtures
from cloudhub.releases import begin,activate,publish
from cloudhub.s3_driver import S3Driver
from cloudhub.s3_files import sha
from cloudhub.errors import HubError
from test_s3 import SETTINGS
from cloudhub.content_routing import routing_code,PUBLIC_PREFIX
import io


class CloudFront:
    def __init__(self,bucket):
        self.config={'Enabled':True,'Origins':{'Quantity':1,'Items':[{'Id':'private-s3','DomainName':bucket+'.s3.us-east-1.amazonaws.com','OriginPath':''}]},'Comment':'keep-complete-config',
            'DefaultCacheBehavior':{'FunctionAssociations':{'Items':[{'EventType':'viewer-request','FunctionARN':'arn:aws:cloudfront::123456789012:function/cloudhub-env-'+'a'*24+'-content'}]}}}
        self.updates=0
        self.live=self.development=routing_code().encode();self.active='initial';self.lose_publish=False
    def get_distribution_config(self,**kw):return {'DistributionConfig':deepcopy(self.config),'ETag':'version-1'}
    def update_distribution(self,**kw):self.config=deepcopy(kw['DistributionConfig']);self.updates+=1
    def get_distribution(self,**kw):return {'Distribution':{'Status':'Deployed','DomainName':'dexample.cloudfront.net'}}
    def get_function(self,**kw):return {'FunctionCode':io.BytesIO(self.live if kw['Stage']=='LIVE' else self.development),'ETag':'v1'}
    def describe_function(self,**kw):return {'ETag':'v1','FunctionSummary':{'FunctionConfig':{'Runtime':'cloudfront-js-2.0','Comment':'preserve-function-config'}}}
    def update_function(self,**kw):
        assert kw['FunctionConfig']['Comment']=='preserve-function-config'
        self.development=kw['FunctionCode'];self.updates+=1;return {'ETag':'v2'}
    def publish_function(self,**kw):
        self.live=self.development;self.active=json.loads(self.live.decode().split(';')[0].removeprefix('var active='))
        if self.lose_publish:self.lose_publish=False;raise TimeoutError('response lost')

import json

def probe(cf,s3,bucket,wrong=False):
    def get(url,limit):
        path=url.split('.cloudfront.net')[1]
        if path=='/':return 302,{'location':PUBLIC_PREFIX+cf.active+'/index.html'},b''
        rid,key=path.removeprefix(PUBLIC_PREFIX).split('/',1)
        physical=key if rid=='initial' else '.cloudhub/releases/'+rid+'/'+key
        return 200,{},b'incorrect cache' if wrong else s3.get_object(Bucket=bucket,Key=physical)['Body'].read()
    return get


class ReleaseTests(TestCase):
    setUp=fixtures.UploadTests.setUp
    def test_prepare_verify_activate_and_rollback_preserve_old_content(self):
        env=self.s.store.get(self.env['pk']);env.update(template_id='T02',distribution_id='EOWNED',direct_upload_schema=1);self.s.save(env)
        initial={'index.html':(b'<link href="style.css"><script src="app.js"></script><img src="pic.png">','text/html'),
                 'app.js':(b'console.log("A")','application/javascript'),'style.css':(b'A{}','text/css'),'pic.png':(b'picture-A','image/png')}
        for key,(data,typ) in initial.items():self.s3.put_object(Bucket=self.bucket,Key=key,Body=data,ContentType=typ)
        rid=begin(self.s,'alice',env['environment_id'],'release-key-1',{})['release_id']
        path='.cloudhub/releases/'+rid+'/index.html';data=b'new website'*4000
        self.s3.put_object(Bucket=self.bucket,Key=path,Body=data,ContentType='text/html',Metadata={'sha256':sha(data)})
        for key,(old,typ) in initial.items():
            if key!='index.html':self.s3.put_object(Bucket=self.bucket,Key='.cloudhub/releases/'+rid+'/'+key,Body=old+b'B',ContentType=typ,Metadata={'sha256':sha(old+b'B')})
        op=activate(self.s,'alice',env['environment_id'],'activate-key-1',{'release_id':rid,'confirmed':True})
        env=self.s.store.get(env['pk']);cf=CloudFront(self.bucket)
        driver=S3Driver(SETTINGS,clients={'s3':self.s3,'cloudfront':cf,'cloudformation':object(),'scheduler':object()},clock=lambda:self.now)
        driver.public_probe=probe(cf,self.s3,self.bucket)
        for _ in range(5):
            if publish(driver,env,op):break
        self.assertEqual(rid,env['active_release_id']);self.assertEqual('initial',env['previous_release_id']);self.assertEqual(1,cf.updates)
        self.assertEqual('keep-complete-config',cf.config['Comment'])
        for key,(data,_) in initial.items():
            self.assertEqual(data,driver.public_probe('https://dexample.cloudfront.net'+PUBLIC_PREFIX+'initial/'+key,5242880)[2])
        self.assertTrue(op['result']['public_content_verified'])
        env['lock']=None;self.s.save(env)
        op=activate(self.s,'alice',env['environment_id'],'rollback-key-1',{'release_id':'initial','confirmed':True})
        env=self.s.store.get(env['pk'])
        for _ in range(5):
            if publish(driver,env,op):break
        self.assertEqual('',env['active_release_prefix']);self.assertEqual(2,cf.updates)
        self.assertEqual({'initial',rid},set(env['published_release_ids']))

    def test_uncertain_publication_blocks_retirement_without_data_loss(self):
        env=self.s.store.get(self.env['pk']);env.update(template_id='T02',publication_uncertain=True,status='ERROR_RETAINED');self.s.save(env)
        q=self.s.management_estimate('alice',env['environment_id'],{'action':'destroy'})
        with self.assertRaises(HubError) as c:self.s.command('alice',env['environment_id'],'destroy','destroy-key-1',{'quote_id':q['quote_id'],'confirmed':True,'expected_revision':0})
        self.assertEqual('PUBLICATION_RECONCILIATION_REQUIRED',c.exception.code)

    def setup_publication(self):
        env=self.s.store.get(self.env['pk']);env.update(template_id='T02',distribution_id='EOWNED',direct_upload_schema=1);self.s.save(env)
        self.s3.put_object(Bucket=self.bucket,Key='index.html',Body=b'old',ContentType='text/html')
        rid=begin(self.s,'alice',env['environment_id'],'release-key-1',{})['release_id']
        self.s3.put_object(Bucket=self.bucket,Key='.cloudhub/releases/'+rid+'/index.html',Body=b'new',ContentType='text/html',Metadata={'sha256':sha(b'new')})
        op=activate(self.s,'alice',env['environment_id'],'activate-key-1',{'release_id':rid,'confirmed':True});env=self.s.store.get(env['pk']);cf=CloudFront(self.bucket)
        driver=S3Driver(SETTINGS,clients={'s3':self.s3,'cloudfront':cf,'cloudformation':object(),'scheduler':object()})
        driver.public_probe=probe(cf,self.s3,self.bucket)
        return env,op,cf,driver

    def test_deployed_is_not_enough_when_public_checksum_is_wrong(self):
        env,op,cf,driver=self.setup_publication();driver.public_probe=probe(cf,self.s3,self.bucket,wrong=True)
        for _ in range(4):self.assertFalse(publish(driver,env,op))
        self.assertTrue(env['publication_uncertain']);self.assertNotIn('result',op);self.assertEqual(1,cf.updates)

    def test_lost_publish_response_reconciles_without_another_update(self):
        env,op,cf,driver=self.setup_publication();cf.lose_publish=True
        with self.assertRaises(TimeoutError):publish(driver,env,op)
        self.assertTrue(publish(driver,env,op));self.assertEqual(1,cf.updates)

    def test_manifest_from_dynamodb_decimals_verifies_with_stable_digest(self):
        from decimal import Decimal
        env,op,cf,driver=self.setup_publication()
        self.assertFalse(publish(driver,env,op))
        original=deepcopy(op['release_manifest'])
        for entry in op['release_manifest']:entry['size']=Decimal(entry['size'])
        self.assertTrue(publish(driver,env,op))
        self.assertEqual(sha(json.dumps(original,sort_keys=True).encode()),op['result']['manifest_sha256'])

    def test_retry_clears_error_only_after_public_content_verification(self):
        env,op,cf,driver=self.setup_publication()
        env.update(status='ERROR_RETAINED',needs_admin=True)
        driver.public_probe=probe(cf,self.s3,self.bucket,wrong=True)
        for _ in range(3):self.assertFalse(publish(driver,env,op))
        self.assertEqual('ERROR_RETAINED',env['status']);self.assertTrue(env['needs_admin'])
        driver.public_probe=probe(cf,self.s3,self.bucket)
        self.assertTrue(publish(driver,env,op))
        self.assertEqual('READY',env['status']);self.assertFalse(env['needs_admin'])

    def test_root_relative_assets_fail_before_switch(self):
        from cloudhub.content_routing import validate_links
        for typ,data in [('text/html',b'<script src="/app.js"></script>'),('text/css',b'a{background:url(/pic.png)}'),('text/javascript',b'fetch("/asset.json")')]:
            with self.assertRaises(HubError):validate_links(data,typ)
        validate_links(b'<script src="app.js"></script>','text/html')

    def test_publication_error_identifies_file_and_path_without_query_secrets(self):
        from cloudhub.content_routing import validate_links
        with self.assertRaises(HubError) as raised:validate_links(b'<script src="/app.js?private=not-public"></script>','text/html','pages/index.html')
        self.assertEqual({'file':'pages/index.html','asset_path':'/app.js'},raised.exception.details)

    def test_bounded_failed_publish_never_fakes_ready_or_drops_old_versions(self):
        env,op,cf,driver=self.setup_publication()
        def fail(**kwargs):raise TimeoutError('no confirmed publication')
        cf.publish_function=fail
        for _ in range(3):
            with self.assertRaises(TimeoutError):publish(driver,env,op)
        with self.assertRaises(HubError) as c:publish(driver,env,op)
        self.assertEqual('PUBLICATION_RECONCILIATION_REQUIRED',c.exception.code)
        self.assertEqual(1,cf.updates);self.assertTrue(env['publication_uncertain']);self.assertNotIn('result',op)

    def test_immutable_initial_content_stays_protected_when_global_feature_is_closed(self):
        import base64
        env=self.s.store.get(self.env['pk']);env.update(template_id='T02',direct_upload_schema=1);self.s.save(env)
        self.s.direct_upload_enabled=False
        with self.assertRaises(HubError) as c:self.s.write_file('alice',env['environment_id'],'inline-write-key',{'key':'index.html','content_type':'text/html','content_base64':base64.b64encode(b'changed').decode()})
        self.assertEqual('RELEASE_REQUIRED',c.exception.code)

    def test_guard_audit_treats_native_not_found_as_deleted(self):
        from test_s3 import AwsError
        class MissingFunction:
            def describe_function(self,**kw):
                assert kw['Stage']=='DEVELOPMENT'
                raise AwsError('NoSuchFunctionExists')
        env=self.s.store.get(self.env['pk']);env['resources']=[{'type':'AWS::CloudFront::Function','id':'cloudhub-'+env['environment_id']+'-content'}]
        driver=S3Driver(SETTINGS,clients={'s3':self.s3,'cloudfront':MissingFunction(),'cloudformation':object(),'scheduler':object()},clock=lambda:self.now)
        driver.assert_stack=lambda env:None
        report=driver.audit(env,[])
        self.assertTrue(any(x['type']=='AWS::CloudFront::Function' for x in report['deleted']))
        self.assertFalse(report['unknown'])
