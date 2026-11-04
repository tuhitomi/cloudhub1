"""Direct, checksummed S3 POST into isolated staging; commit via the durable worker."""
import base64
import hashlib
import re
from .catalog import environment_configuration
from .errors import HubError
from .s3_files import OwnedFiles, MIME_TYPES, assert_bucket, objects, validate_key, error_code, read, sha


class Uploads(OwnedFiles):
    def enabled(self):
        if not self.service.direct_upload_enabled:
            raise HubError('UPLOAD_DISABLED','Direct uploads have not been enabled and verified by the administrator.',409)

    def initiate(self, owner, eid, key, body):
        self.enabled()
        from .service import ident,expected,retry
        if set(body)-{'key','size','sha256','content_type','expected_version','release_id'} or not {'key','size','sha256','content_type'}<=set(body):
            raise HubError('INVALID_INPUT','File name, exact size, SHA-256 and MIME type are required.')
        validate_key(body['key'])
        if type(body['size']) is not int or body['size']<1 or not re.fullmatch('[a-f0-9]{64}',str(body['sha256'])) or body['content_type'] not in MIME_TYPES:
            raise HubError('INVALID_INPUT','Invalid upload size, checksum or content type.')
        def transaction():
            env=self.service.owned('E',eid,owner)
            if not self.service.direct_upload_available(env):raise HubError('UPLOAD_UNVERIFIED','Direct uploads have not been verified in this Region.',409)
            if env['template_id']=='T02' and env.get('direct_upload_schema')!=1:raise HubError('UPLOAD_MIGRATION_REQUIRED','Create a verified environment with protected release routing before enabling uploads.',409)
            ipk,fp,old=self.service.idempotency(owner,key,eid+'/upload',body)
            if old:
                return self.service.owned('H',old['upload_id'],owner)
            self._ready(env)
            limits=environment_configuration(env)
            if body['size']>limits['max_file_bytes']:raise HubError('FILE_QUOTA','File exceeds the selected configuration.',413)
            if int(env.get('upload_grants_used',0))>=limits['max_writes']:raise HubError('FILE_QUOTA','Upload write quota reached.',409)
            self.prepare(env);bucket=assert_bucket(self.client,env,self.settings)
            if not bucket:raise HubError('SOURCE_MISSING','Source bucket is missing.',409)
            prefix=env.get('active_release_prefix','')
            if env['template_id']=='T02':
                if not body.get('release_id') or body['release_id']!=env.get('draft_release_id'):
                    raise HubError('RELEASE_REQUIRED','Prepare a new website release before uploading content.',409)
                prefix='.cloudhub/releases/'+body['release_id']+'/'
            entries=objects(self.client,bucket,self.settings,limits,prefix=prefix)
            current=next((v for v in entries if v['key']==body['key']),None)
            if current:
                meta=self.client.head_object(Bucket=bucket,Key=prefix+body['key'],ExpectedBucketOwner=self.settings['account_id'])
                if not body.get('expected_version') or body['expected_version']!=meta.get('VersionId'):
                    raise HubError('FILE_CONFLICT','Confirm replacement of the current object version.',409)
            elif body.get('expected_version'):raise HubError('FILE_CONFLICT','The expected object no longer exists.',409)
            if len(entries)+(0 if current else 1)>limits['max_files'] or sum(v['size'] for v in entries)-(current['size'] if current else 0)+body['size']>limits['max_total_bytes']:
                raise HubError('FILE_QUOTA','The upload exceeds the file count or total storage quota.',413)
            uid=ident('upload-',ipk);now=int(self.service.clock())
            row={'pk':'H#'+uid,'kind':'upload','owner_id':owner,'owner_sort':'upload#'+uid,
                 'upload_id':uid,'environment_id':eid,'region':self.service.region_for(env),'created_at':now,
                 'expires_at':now+120,'complete_until':now+720,'status':'PENDING','file':body,
                 'destination_prefix':prefix,'bucket':self.settings['s3_backup_bucket'],
                 'staging_key':'uploads/'+eid+'/'+uid,'expected_destination_version':body.get('expected_version')}
            env['lock']=uid;env['upload_expires_at']=row['complete_until'];env['upload_grants_used']=int(env.get('upload_grants_used',0))+1
            idem={'pk':ipk,'fingerprint':fp,'upload_id':uid}
            self.service.store.commit([row,env,idem],expected(row,env,idem))
            return self.service.store.get(row['pk'])
        row=retry(transaction)
        if row['status']!='PENDING' or row['expires_at']<=self.service.clock():
            raise HubError('UPLOAD_EXPIRED','The upload grant expired. Inspect the result or start a new upload.',409)
        # A grant is scoped to one staging key, exact bytes/type/checksum, and two minutes.
        # S3 validates SHA-256; retries can only upload identical bytes to that staging key.
        env=self.service.owned('E',eid,owner);self.prepare(env)
        checksum=base64.b64encode(bytes.fromhex(row['file']['sha256'])).decode()
        fields={'Content-Type':row['file']['content_type'],'x-amz-server-side-encryption':'AES256',
                'x-amz-checksum-algorithm':'SHA256','x-amz-checksum-sha256':checksum,'success_action_status':'201'}
        grant=self.client.generate_presigned_post(Bucket=row['bucket'],Key=row['staging_key'],Fields=fields,
            Conditions=[{'key':row['staging_key']},['content-length-range',int(row['file']['size']),int(row['file']['size'])],
                *[{k:v} for k,v in fields.items()]],ExpiresIn=max(1,int(row['expires_at'])-int(self.service.clock())))
        return {'upload_id':row['upload_id'],'post':grant,'expires_at':row['expires_at'],'complete_until':row['complete_until'],
                'limits':environment_configuration(env),'contains_temporary_capability':True}

    def cancel(self,owner,eid,uid,key,body):
        if body:raise HubError('INVALID_INPUT','No cancellation fields are accepted.')
        from .service import expected,retry
        def transaction():
            env=self.service.owned('E',eid,owner);row=self.service.owned('H',uid,owner)
            if row['environment_id']!=eid:raise HubError('NOT_FOUND','Upload not found.',404)
            if row.get('operation_id'):return {'operation_id':self.service.owned('O',row['operation_id'],owner)['operation_id']}
            ipk,fp,old=self.service.idempotency(owner,key,eid+'/cancel-upload/'+uid,{})
            if old:return {'status':'CANCELLED'}
            if env.get('lock')==uid:env['lock']=None
            row['status']='CANCELLED'
            idem={'pk':ipk,'fingerprint':fp,'upload_id':uid}
            self.service.store.commit([env,row,idem],expected(env,row,idem));return {'status':'CANCELLED','staging_expires_automatically':True}
        return retry(transaction)

    def _ready(self,env):
        if env['template_id'] not in {'T02','T07'} or env['status']!='READY' or env.get('lock') or (env.get('deadline') is not None and env['deadline']<=self.service.clock()):
            raise HubError('OPERATION_LOCKED','The environment is not ready for an upload.',409)

    def complete(self,owner,eid,uid,key,body):
        if body:raise HubError('INVALID_INPUT','No upload completion fields are accepted.')
        from .service import ident,record,expected,retry
        def transaction():
            env=self.service.owned('E',eid,owner);row=self.service.owned('H',uid,owner)
            if row['environment_id']!=eid:raise HubError('NOT_FOUND','Upload not found.',404)
            _,_,old=self.service.idempotency(owner,key,eid+'/complete-upload/'+uid,{})
            if old:return self.service.owned('O',old['operation_id'],owner)
            if row['status']=='ACCEPTED':return self.service.owned('O',row['operation_id'],owner)
            self.enabled()
            if row['status']!='PENDING' or row['complete_until']<=self.service.clock() or env.get('lock')!=uid or (env.get('deadline') is not None and env['deadline']<=self.service.clock()):
                raise HubError('UPLOAD_EXPIRED','Upload is no longer pending.',409)
            self.prepare(env)
            try:
                meta=self.client.head_object(Bucket=row['bucket'],Key=row['staging_key'],ExpectedBucketOwner=self.settings['account_id'],ChecksumMode='ENABLED')
            except Exception as exc:
                if error_code(exc) in {'404','NoSuchKey','NotFound'}:
                    raise HubError('UPLOAD_INCOMPLETE','Upload has not finished. Retry the upload or cancel it before confirming.',409) from None
                if error_code(exc) in {'403','AccessDenied','Forbidden'}:
                    # Without ListBucket, a missing staging object also returns
                    # 403. Do not expand IAM or claim the object was verified.
                    raise HubError('UPLOAD_NOT_VISIBLE','The staged file cannot be verified yet. Retry the transfer or cancel it; if already uploaded, contact the administrator. Live data is preserved.',409) from None
                raise
            digest=base64.b64encode(bytes.fromhex(row['file']['sha256'])).decode()
            if meta.get('ContentLength')!=row['file']['size'] or meta.get('ChecksumSHA256')!=digest or meta.get('ContentType')!=row['file']['content_type'] or not meta.get('ETag'):
                raise HubError('UPLOAD_MISMATCH','Uploaded object does not match its approved size, type and checksum.',409)
            ipk,fp,_=self.service.idempotency(owner,key,eid+'/complete-upload/'+uid,{})
            # The retained backup bucket can be unversioned. Each grant binds one
            # unique key to exact size/type/SHA bytes, so a valid POST replay can
            # only write identical content. Fence the worker GET with ETag and
            # always verify the approved SHA; retain VersionId where available.
            oid=ident('op-',ipk);row.update(status='ACCEPTED',operation_id=oid,
                source_version=meta.get('VersionId') if meta.get('VersionId')!='null' else None,
                source_etag=meta['ETag'],source_pin='VERSION_SHA256' if meta.get('VersionId') not in {None,'null'} else 'ETAG_SHA256')
            op=record('operation',oid,owner,operation_id=oid,job_id=oid,environment_id=eid,region=self.service.region_for(env),
                action='commit_upload',phase='COMMIT_UPLOAD',status='QUEUED',attempts=0,events=[],created_at=int(self.service.clock()),upload_id=uid)
            env['lock']=oid;env['file_writes']=int(env.get('file_writes',0))+1
            rows=[env,row,op,{'pk':ipk,'fingerprint':fp,'operation_id':oid}]
            self.service.store.commit(rows,expected(*rows));return self.service.store.get(op['pk'])
        return retry(transaction)


def commit_upload(driver,env,op,upload):
    """Bounded worker I/O, pinned source version and conditional destination write."""
    if upload['owner_id']!=env['owner_id'] or upload['environment_id']!=env['environment_id'] or upload['status'] not in {'ACCEPTED','COMMITTED'} or upload['operation_id']!=op['operation_id']:
        raise HubError('RESOURCE_SCOPE_MISMATCH','Upload does not belong to this operation.',409)
    bucket=driver._source(env);account=driver.settings['account_id'];key=upload['destination_prefix']+upload['file']['key']
    if upload['status']=='COMMITTED':
        actual,meta=read(driver.s3,bucket,key,account,limit=environment_configuration(env)['max_file_bytes'])
        if sha(actual)!=upload['file']['sha256'] or len(actual)!=upload['file']['size'] or meta.get('Metadata',{}).get('cloudhub-operation')!=op['operation_id']:
            raise HubError('UPLOAD_MISMATCH','Committed destination changed; preserve source data.',409)
        op['result']={'key':upload['file']['key'],'size':len(actual),'sha256':sha(actual),'data_verified':True};return
    try:
        data,response=read(driver.s3,upload['bucket'],upload['staging_key'],account,upload.get('source_version'),
            limit=environment_configuration(env)['max_file_bytes'],if_match=upload.get('source_etag'))
    except Exception as exc:
        if error_code(exc) in {'PreconditionFailed','412','NoSuchVersion','NoSuchKey'}:
            raise HubError('UPLOAD_MISMATCH','Staged content changed after confirmation; source data is preserved.',409) from None
        raise
    if len(data)!=upload['file']['size'] or sha(data)!=upload['file']['sha256']:raise HubError('UPLOAD_MISMATCH','Staged bytes do not match the approved checksum.',409)
    try:current=driver.s3.head_object(Bucket=bucket,Key=key,ExpectedBucketOwner=account)
    except Exception as e:
        if error_code(e) not in {'404','NoSuchKey'}:raise
        current=None
    if current and current.get('Metadata',{}).get('cloudhub-operation')==op['operation_id']:
        actual,_=read(driver.s3,bucket,key,account,limit=environment_configuration(env)['max_file_bytes'])
        if sha(actual)!=sha(data):raise HubError('UPLOAD_MISMATCH','Previously committed content does not match.',409)
    else:
        entries=objects(driver.s3,bucket,driver.settings,environment_configuration(env),prefix=upload['destination_prefix'])
        others=[entry for entry in entries if entry['key']!=upload['file']['key']]
        limits=environment_configuration(env)
        if len(others)+1>limits['max_files'] or sum(x['size'] for x in others)+len(data)>limits['max_total_bytes']:
            raise HubError('FILE_QUOTA','Storage changed after upload approval; source is preserved.',409)
        expected=upload.get('expected_destination_version')
        if (current.get('VersionId') if current else None)!=expected:raise HubError('FILE_CONFLICT','Destination changed after upload approval.',409)
        condition={'IfMatch':current['ETag']} if current else {'IfNoneMatch':'*'}
        driver.s3.put_object(Bucket=bucket,Key=key,Body=data,ContentType=upload['file']['content_type'],
            Metadata={'sha256':sha(data),'cloudhub-operation':op['operation_id']},ServerSideEncryption='AES256',ExpectedBucketOwner=account,**condition)
        actual,_=read(driver.s3,bucket,key,account,limit=environment_configuration(env)['max_file_bytes'])
        if sha(actual)!=sha(data):raise HubError('UPLOAD_MISMATCH','Destination checksum does not match.',409)
    upload.update(status='COMMITTED',committed_at=int(driver.clock()))
    op['result']={'key':upload['file']['key'],'size':len(data),'sha256':sha(data),'data_verified':True}


def expire_upload(service,eid):
    from .service import expected,retry
    def transaction():
        env=service.store.get('E#'+eid)
        if not env or not str(env.get('lock','')).startswith('upload-'):return
        upload=service.store.get('H#'+env['lock'])
        if not upload or upload['owner_id']!=env['owner_id']:raise HubError('UPLOAD_SCOPE_MISMATCH','Upload lease needs administrator review.',409)
        if upload['status']=='PENDING' and upload['complete_until']<=service.clock():
            upload['status']='EXPIRED';env['lock']=None
            service.store.commit([upload,env],expected(upload,env))
    return retry(transaction)
