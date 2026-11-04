"""Large-object upload, backup and restore with local S3 doubles; no AWS proof."""
import base64
import hashlib
from copy import deepcopy
from unittest import TestCase
from test_s3 import FakeS3, SETTINGS, RATES, AwsError
from cloudhub.uploads import Uploads, commit_upload,expire_upload
from cloudhub.service import Service,record
from cloudhub.store import MemoryStore
from cloudhub.cost import Estimator
from cloudhub.catalog import configuration_profiles,configuration_key
from cloudhub.s3_files import bucket_name,objects,read
from cloudhub.s3_driver import S3Driver
from cloudhub.errors import HubError


class UploadS3(FakeS3):
    def generate_presigned_post(self, **kw):
        self.post=kw
        return {'url':'https://staging.example.invalid','fields':kw['Fields']}
    def head_object(self,**kw):
        result=super().head_object(**kw)
        data=super().get_object(**kw)['Body'].read()
        if getattr(self,'unversioned_staging',False) and kw['Bucket']==SETTINGS['s3_backup_bucket']:result.pop('VersionId',None)
        return {**result,'ContentLength':len(data),'ChecksumSHA256':base64.b64encode(hashlib.sha256(data).digest()).decode()}
    def get_object(self,**kw):
        result=super().get_object(**kw)
        if kw.get('IfMatch') and kw['IfMatch']!='"'+hashlib.md5(result['Body'].getvalue()).hexdigest()+'"':raise AwsError('PreconditionFailed')
        return result


class UploadTests(TestCase):
    def setUp(self):
        self.now=1000;self.s=Service(MemoryStore(),clock=lambda:self.now,estimator=Estimator({**RATES,'units':{**RATES['units'],'cloudfront_functions_million':'0.1'}}),verified={'T07'},budget_milliusd=100000,direct_upload_enabled=True)
        cfg=next(p['configuration'] for p in configuration_profiles('T07') if p['id']=='files')
        self.env=record('environment','env-'+'a'*24,'alice',environment_id='env-'+'a'*24,template_id='T07',
            status='READY',deadline=None,region='us-east-1',configuration=cfg,lock=None)
        self.s.regions_config['direct_upload_verifications']={'us-east-1':{tid:{**dict.fromkeys(['passed','backup_restore_verified','content_switch_verified','upload_verified','iam_reviewed'],True),'configuration_keys':[configuration_key(tid,cfg)]} for tid in ['T02','T07']}}
        self.s.save(self.env);self.s3=UploadS3();self.bucket=bucket_name(self.env,SETTINGS)
        self.s3.buckets[self.bucket]={'tags':{'cloudhub:owner':'alice','cloudhub:environment':self.env['environment_id'],'cloudhub:managed':'true'},'files':{}}
        self.u=Uploads(self.s,SETTINGS,client=self.s3)
        self.data=b'file-content-'*50000 # > 8 KiB, without routing bytes through API/DynamoDB
        self.body={'key':'report.txt','size':len(self.data),'content_type':'text/plain','sha256':hashlib.sha256(self.data).hexdigest()}

    def initiate(self):return self.u.initiate('alice',self.env['environment_id'],'upload-key-1',self.body)
    def stage(self):
        grant=self.initiate();row=self.s.store.get('H#'+grant['upload_id'])
        self.s3.put_object(Bucket=row['bucket'],Key=row['staging_key'],Body=self.data,ContentType='text/plain')
        return grant

    def test_signed_post_exact_limits_and_foreign_owner_rejected(self):
        g=self.initiate();self.assertIn(['content-length-range',len(self.data),len(self.data)],self.s3.post['Conditions'])
        self.assertEqual(120,self.s3.post['ExpiresIn']);self.assertNotIn('amazonaws.com',g['post']['url']) # local fake
        with self.assertRaises(HubError):self.u.initiate('bob',self.env['environment_id'],'upload-key-1',self.body)
        self.assertEqual(g,self.initiate())

    def test_replayed_dynamodb_decimal_expiry_is_integer_for_sdk_signing(self):
        from decimal import Decimal
        grant=self.initiate();row=self.s.store.get('H#'+grant['upload_id'])
        row['expires_at']=Decimal(row['expires_at']);self.s.save(row)
        again=self.initiate();self.assertEqual(grant['upload_id'],again['upload_id'])
        self.assertIs(type(self.s3.post['ExpiresIn']),int)

    def test_dynamodb_roundtrip_and_real_local_sdk_post_signer(self):
        import boto3,json
        from boto3.dynamodb.types import TypeSerializer,TypeDeserializer
        from botocore.config import Config
        original=self.s.store.get
        self.s.store.get=lambda pk:TypeDeserializer().deserialize(TypeSerializer().serialize(original(pk)))
        signer=boto3.client('s3',region_name='us-east-1',aws_access_key_id='fixture',aws_secret_access_key='fixture',
            config=Config(signature_version='s3v4'))
        self.s3.generate_presigned_post=signer.generate_presigned_post
        grant=self.initiate();policy=json.loads(base64.b64decode(grant['post']['fields']['policy']))
        sizes=next(c for c in policy['conditions'] if isinstance(c,list) and c[0]=='content-length-range')
        self.assertEqual(['content-length-range',len(self.data),len(self.data)],sizes)
        self.assertIs(type(sizes[1]),int)
        self.assertEqual(grant['upload_id'],self.initiate()['upload_id'])

    def test_t07_proof_cannot_open_t02_or_another_region(self):
        proofs=self.s.regions_config['direct_upload_verifications']['us-east-1']
        proofs.pop('T02');self.assertTrue(self.s.direct_upload_available(self.env))
        self.assertFalse(self.s.direct_upload_available({**self.env,'template_id':'T02'}))
        self.assertFalse(self.s.direct_upload_available({**self.env,'region':'ap-southeast-1'}))
        self.assertFalse(self.s.direct_upload_available({'region':'us-east-1'}))
        self.assertFalse(self.s.direct_upload_available({**self.env,'configuration':None}))

    def test_oversized_and_wrong_checksum_completion_are_rejected(self):
        with self.assertRaises(HubError):self.u.initiate('alice',self.env['environment_id'],'oversize-key',{**self.body,'size':6*1024*1024})
        g=self.stage();row=self.s.store.get('H#'+g['upload_id']);row['file']['sha256']='0'*64;self.s.save(row)
        with self.assertRaises(HubError):self.u.complete('alice',self.env['environment_id'],g['upload_id'],'complete-key',{})
        self.assertEqual([],self.s.store.list_owner('alice','operation'))

    def test_incomplete_upload_can_resume_with_same_grant_and_key(self):
        grant=self.initiate();eid=self.env['environment_id']
        with self.assertRaises(HubError) as raised:self.u.complete('alice',eid,grant['upload_id'],'complete-key',{})
        self.assertEqual('UPLOAD_INCOMPLETE',raised.exception.code)
        self.assertEqual([],self.s.store.list_owner('alice','operation'))
        row=self.s.store.get('H#'+grant['upload_id']);self.assertEqual('PENDING',row['status'])
        self.s3.put_object(Bucket=row['bucket'],Key=row['staging_key'],Body=self.data,ContentType='text/plain')
        result=self.u.complete('alice',eid,grant['upload_id'],'complete-key',{})
        self.assertEqual('QUEUED',result['status'])

    def test_head_forbidden_is_ambiguous_pending_and_preserves_live_data(self):
        grant=self.initiate();eid=self.env['environment_id'];head=self.s3.head_object
        for code in ['403','AccessDenied','Forbidden']:
            with self.subTest(code=code):
                def denied(**kw):raise AwsError(code)
                self.s3.head_object=denied
                with self.assertRaises(HubError) as raised:self.u.complete('alice',eid,grant['upload_id'],'complete-key',{})
                self.assertEqual('UPLOAD_NOT_VISIBLE',raised.exception.code)
                self.assertEqual('PENDING',self.s.store.get('H#'+grant['upload_id'])['status'])
                self.assertEqual(grant['upload_id'],self.s.store.get(self.env['pk'])['lock'])
                self.assertEqual([],self.s.store.list_owner('alice','operation'))
                self.assertEqual({},self.s3.buckets[self.bucket]['files'])
        self.s3.head_object=head
        self.assertEqual('CANCELLED',self.u.cancel('alice',eid,grant['upload_id'],'cancel-key',{})['status'])

    def test_commit_retry_large_backup_and_restore_match_bytes(self):
        g=self.stage();eid=self.env['environment_id'];op=self.u.complete('alice',eid,g['upload_id'],'complete-key',{})
        same=self.u.complete('alice',eid,g['upload_id'],'complete-key',{});self.assertEqual(op,same)
        row=self.s.store.get('H#'+g['upload_id']);env=self.s.store.get(self.env['pk'])
        driver=S3Driver(SETTINGS,clients={'s3':self.s3,'cloudformation':object(),'cloudfront':object(),'scheduler':object()},clock=lambda:self.now)
        commit_upload(driver,env,op,row);row['status']='ACCEPTED';commit_upload(driver,env,op,row)
        actual,_=read(self.s3,self.bucket,'report.txt',SETTINGS['account_id'],limit=env['configuration']['max_file_bytes']);self.assertEqual(self.data,actual)
        rp={'recovery_point':'rp-'+'b'*24,'owner_id':'alice','environment_id':eid,'template_id':'T07','configuration':env['configuration']}
        backup={}
        for _ in range(10):
            if driver.backup(env,backup,rp):break
        restored={**env,'environment_id':'env-'+'c'*24};target=bucket_name(restored,SETTINGS)
        self.s3.buckets[target]={'tags':{},'files':{}}
        restore={"operation_id":"op-restore"}
        for _ in range(10):
            if driver._restore(restored,restore,rp,target):break
        actual,_=read(self.s3,target,'report.txt',SETTINGS['account_id'],limit=env['configuration']['max_file_bytes']);self.assertEqual(self.data,actual)

    def test_unversioned_staging_is_checksum_and_etag_pinned_without_bucket_changes(self):
        self.s3.unversioned_staging=True
        grant=self.stage();eid=self.env['environment_id']
        op=self.u.complete('alice',eid,grant['upload_id'],'complete-key',{})
        row=self.s.store.get('H#'+grant['upload_id']);self.assertIsNone(row['source_version'])
        self.assertEqual('ETAG_SHA256',row['source_pin'])
        driver=S3Driver(SETTINGS,clients={'s3':self.s3,'cloudformation':object(),'cloudfront':object(),'scheduler':object()})
        commit_upload(driver,self.s.store.get(self.env['pk']),op,row)
        gets=[kw for action,kw in self.s3.calls if action=='get_object' and kw['Key']==row['staging_key']]
        self.assertEqual(row['source_etag'],gets[-1]['IfMatch']);self.assertNotIn('VersionId',gets[-1])
        actual,_=read(self.s3,self.bucket,'report.txt',SETTINGS['account_id'],limit=len(self.data))
        self.assertEqual(self.data,actual)

    def test_changed_unversioned_staging_never_writes_destination(self):
        self.s3.unversioned_staging=True
        grant=self.stage();op=self.u.complete('alice',self.env['environment_id'],grant['upload_id'],'complete-key',{})
        row=self.s.store.get('H#'+grant['upload_id'])
        self.s3.put_object(Bucket=row['bucket'],Key=row['staging_key'],Body=b'changed outside approved grant',ContentType='text/plain')
        driver=S3Driver(SETTINGS,clients={'s3':self.s3,'cloudformation':object(),'cloudfront':object(),'scheduler':object()})
        with self.assertRaises(HubError) as raised:commit_upload(driver,self.s.store.get(self.env['pk']),op,row)
        self.assertEqual('UPLOAD_MISMATCH',raised.exception.code)
        self.assertNotIn('report.txt',self.s3.buckets[self.bucket]['files'])

    def test_accepted_completion_replay_survives_feature_closure_and_still_checks_owner(self):
        grant=self.stage();eid=self.env['environment_id']
        op=self.u.complete('alice',eid,grant['upload_id'],'complete-key',{})
        self.s.direct_upload_enabled=False;self.now+=1000
        self.assertEqual(op,self.u.complete('alice',eid,grant['upload_id'],'complete-key',{}))
        with self.assertRaises(HubError) as raised:self.u.complete('bob',eid,grant['upload_id'],'complete-key',{})
        self.assertEqual('NOT_FOUND',raised.exception.code)

    def test_failed_or_expired_grant_never_changes_live_data(self):
        g=self.initiate();self.now+=721;expire_upload(self.s,self.env['environment_id'])
        self.assertIsNone(self.s.store.get(self.env['pk'])['lock'])
        self.assertEqual({},self.s3.buckets[self.bucket]['files'])
        with self.assertRaises(HubError):self.u.complete('alice',self.env['environment_id'],g['upload_id'],'complete-key',{})

    def test_new_large_configuration_is_not_opened_without_native_proof(self):
        body={'template_id':'T07','duration_hours':1,'configuration':self.env['configuration']}
        with self.assertRaises(HubError) as c:self.s.create_estimate('alice',body)
        self.assertEqual('CONFIGURATION_UNVERIFIED',c.exception.code)

    def test_closing_direct_gate_also_closes_new_files_profile_admission(self):
        from cloudhub.catalog import configuration_key
        cfg=self.env['configuration'];self.s.estimator.rates.setdefault('configuration_verifications',{})[configuration_key('T07',cfg)]={'passed':True,'provisioning_checks':2,'backup_restore_verified':True}
        self.assertTrue(self.s.configuration_is_verified('T07',cfg))
        self.s.direct_upload_enabled=False
        self.assertFalse(self.s.configuration_is_verified('T07',cfg))
        profile=next(p for r in self.s.region_options('T07') if r['region']=='us-east-1' for p in r['configuration_options'] if p['id']=='files')
        self.assertFalse(profile['create_enabled']);self.assertEqual('UNAVAILABLE',profile['status'])

    def test_cancel_releases_pending_lease_without_touching_source(self):
        g=self.stage();eid=self.env['environment_id'];result=self.u.cancel('alice',eid,g['upload_id'],'cancel-upload-key',{})
        self.assertEqual('CANCELLED',result['status']);self.assertIsNone(self.s.store.get(self.env['pk'])['lock'])
        self.assertEqual({},self.s3.buckets[self.bucket]['files'])
        self.assertEqual('CANCELLED',self.u.cancel('alice',eid,g['upload_id'],'cancel-upload-key',{})['status'])

    def test_owned_listing_exposes_only_pending_metadata_for_reload_cancel(self):
        grant=self.initiate();eid=self.env['environment_id'];pending=self.u.list('alice',eid)['pending_upload']
        self.assertEqual(grant['upload_id'],pending['upload_id']);self.assertTrue(pending['can_cancel'])
        self.assertEqual(self.body['key'],pending['key']);self.assertNotIn('post',pending)
        with self.assertRaises(HubError):self.u.list('bob',eid)
        self.u.cancel('alice',eid,grant['upload_id'],'cancel-key',{})
        self.assertIsNone(self.u.list('alice',eid)['pending_upload'])
