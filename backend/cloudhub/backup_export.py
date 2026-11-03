"""Portable datasets and explicit native-snapshot references, never fake downloads."""
import io,json,zipfile,tempfile,time
from concurrent.futures import ThreadPoolExecutor
from .errors import HubError
from .s3_driver import canonical

class BackupExports:
    def __init__(self, settings, router):self.settings,self.router=settings,router

    def export(self, env, op, rp):
        from .regions import regional_settings
        settings=regional_settings(self.settings,rp)
        driver=self.router.driver(rp);kind=rp['template_id'];s3=getattr(driver,'s3',None)
        if s3 is None:
            import boto3
            from botocore.config import Config
            s3=boto3.client('s3',region_name=settings['region'],config=Config(connect_timeout=2,read_timeout=3,retries={'total_max_attempts':1}))
        reference={k:rp[k] for k in ['recovery_point','environment_id','template_id','created_at','retain_until','scope','manifest_sha256','snapshot_id','db_snapshot_id','redshift_snapshot_arn','recovery_point_arn','aws_recovery_point_arn'] if k in rp}
        full=kind in {'T02','T06','T07','T09'}
        def persist(data,extension,typ,size):
            key='recovery/'+rp['recovery_point']+'/exports/'+op['operation_id']+'.'+extension
            s3.put_object(Bucket=settings['s3_backup_bucket'],Key=key,Body=data,ContentType=typ,
                ServerSideEncryption='AES256',ExpectedBucketOwner=self.settings['account_id'],
                Metadata={'cloudhub-owner':env['owner_id'],'cloudhub-environment':env['environment_id'],'cloudhub-recovery':rp['recovery_point']})
            return {'export_key':key,'filename':rp['recovery_point']+'.'+extension,'contains_all_protected_data':full,
                'label':'Tải dữ liệu bản sao' if full else 'Tải dữ liệu S3 và thông tin snapshot' if kind=='T10' else 'Tải thông tin snapshot',
                'bytes':size}
        if kind in {'T02','T06','T07','T10'}:
            from .catalog import environment_configuration
            files=driver.file_driver() if kind in {'T06','T10'} else driver
            entries=files._manifest(rp,env['owner_id'])
            limit=environment_configuration(rp)['max_file_bytes']
            def content(item):
                from .s3_files import sha
                blob,_=files._bytes(settings['s3_backup_bucket'],files._prefix(rp)+'data/'+item['key'],limit)
                if len(blob)!=item['size'] or sha(blob)!=item['sha256']:raise HubError('BACKUP_CORRUPT','Dữ liệu tải về không khớp bản sao.',409)
                return item['key'],blob
            # Keep at most four bounded files in RAM; spool the ZIP to ephemeral
            # disk instead of holding the 50 MiB dataset, ZIP and upload copy.
            started=time.monotonic()
            with tempfile.SpooledTemporaryFile(max_size=1024*1024,mode='w+b') as buffer:
                with ThreadPoolExecutor(max_workers=4) as pool,zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_STORED) as archive:
                    for cursor in range(0,len(entries),4):
                        if time.monotonic()-started>=40:raise HubError('EXPORT_TIMEOUT','Export did not complete in its time limit. The backup is preserved; retry the operation.',409)
                        contents=list(pool.map(content,entries[cursor:cursor+4]))
                        for name,blob in contents:archive.writestr('data/'+name,blob)
                        del contents
                    archive.writestr('cloudhub-backup.json',canonical(reference))
                size=buffer.tell();buffer.seek(0)
                return persist(buffer,'zip','application/zip',size)
        elif kind=='T09':
            records=driver.load_archive(env,rp)
            data=canonical({'backup':reference,'records':records})
            extension='json';typ='application/json'
        else:
            data=canonical({'backup':reference,'contains_snapshot_data':False,
                'notice':'Đây là thông tin snapshot AWS, không phải file chứa toàn bộ dữ liệu. Dùng Khôi phục trong CloudHub để lấy lại dữ liệu.'})
            extension='json';typ='application/json'
        return persist(data,extension,typ,len(data))

def download(service, owner, oid, settings, client=None):
    op=service.owned('O',oid,owner)
    if op['action']!='export_backup' or op['status']!='SUCCEEDED':raise HubError('INVALID_STATE','Bản tải chưa sẵn sàng.',409)
    rp=service.owned('R',op['recovery_point'],owner)
    from .regions import regional_settings
    settings=regional_settings(settings,{**rp,'region':service.region_for(rp)})
    if rp['status']!='AVAILABLE' or rp['retain_until']<=service.clock() or rp.get('delete_lock'):
        raise HubError('RECOVERY_UNAVAILABLE','Bản sao đã xóa, hết hạn hoặc đang được xóa.',409)
    result=op['result'];key=result['export_key']
    if not key.startswith('recovery/'+rp['recovery_point']+'/exports/'+oid+'.'):
        raise HubError('RESOURCE_SCOPE_MISMATCH','Đường dẫn bản tải không hợp lệ.',409)
    import boto3
    from botocore.config import Config
    s3=client or boto3.client('s3',region_name=settings.get('region'),config=Config(signature_version='s3v4',
        s3={'addressing_style':'virtual'},connect_timeout=1,read_timeout=2,retries={'total_max_attempts':1}))
    info=s3.head_object(Bucket=settings['s3_backup_bucket'],Key=key,ExpectedBucketOwner=settings['account_id'])
    attrs=info.get('Metadata',{})
    if attrs.get('cloudhub-owner')!=owner or attrs.get('cloudhub-recovery')!=rp['recovery_point'] or attrs.get('cloudhub-environment')!=rp['environment_id']:
        raise HubError('RESOURCE_SCOPE_MISMATCH','File xuất không thuộc bản sao.',409)
    ttl=max(1,min(900,int(float(rp['retain_until'])-float(service.clock()))))
    url=s3.generate_presigned_url('get_object',Params={'Bucket':settings['s3_backup_bucket'],'Key':key,
        'ResponseContentDisposition':'attachment; filename="'+result['filename']+'"'},ExpiresIn=ttl)
    return {'url':url,'expires_at':int(service.clock())+ttl,'filename':result['filename'],'label':result['label']}
