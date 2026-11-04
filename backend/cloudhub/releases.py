"""T02 immutable public URLs, bounded function publication and public reconciliation."""
import json
import re
from .catalog import environment_configuration
from .errors import HubError
from .s3_files import objects,read,sha
from .content_routing import routing_code,validate_links,PUBLIC_PREFIX


def begin(service,owner,eid,key,body):
    from .service import ident,expected,retry
    if body:raise HubError('INVALID_INPUT','No release input fields are accepted.')
    if not service.direct_upload_enabled:raise HubError('UPLOAD_DISABLED','Versioned content is not enabled.',409)
    def transaction():
        env=service.owned('E',eid,owner);ipk,fp,old=service.idempotency(owner,key,eid+'/release',{})
        if old:return {'release_id':old['release_id'],'new_environment':False}
        if not service.direct_upload_available(env) or env.get('direct_upload_schema')!=1:raise HubError('UPLOAD_MIGRATION_REQUIRED','Protected release routing must be verified before content releases.',409)
        if env['template_id']!='T02' or env['status']!='READY' or env.get('lock') or env.get('draft_release_id'):
            raise HubError('INVALID_STATE','Finish the current draft or operation first.',409)
        if int(env.get('release_count',0))>=3:raise HubError('RELEASE_QUOTA','Three prepared releases per environment are allowed in this release.',409)
        rid=ident('release-',ipk);env['draft_release_id']=rid;env['release_count']=int(env.get('release_count',0))+1
        idem={'pk':ipk,'fingerprint':fp,'release_id':rid}
        service.store.commit([env,idem],expected(env,idem));return {'release_id':rid,'new_environment':False}
    return retry(transaction)


def activate(service,owner,eid,key,body):
    from .service import ident,record,expected,retry
    if set(body)!={'release_id','confirmed'} or body['confirmed'] is not True:raise HubError('INVALID_INPUT','Confirm the exact release to publish or restore.')
    def transaction():
        env=service.owned('E',eid,owner);ipk,fp,old=service.idempotency(owner,key,eid+'/publish-release',body)
        if old:return service.owned('O',old['operation_id'],owner)
        if not service.direct_upload_available(env) or env.get('direct_upload_schema')!=1 or env['template_id']!='T02' or env['status']!='READY' or env.get('lock'):
            raise HubError('OPERATION_LOCKED','Website content cannot be switched now.',409)
        rid=body['release_id']
        if rid not in {env.get('draft_release_id'),env.get('previous_release_id')} or not rid:
            raise HubError('RELEASE_UNAVAILABLE','Only a prepared draft or previous release can be activated.',409)
        oid=ident('op-',ipk);env['lock']=oid;env['publication_uncertain']=True
        op=record('operation',oid,owner,operation_id=oid,job_id=oid,environment_id=eid,region=service.region_for(env),
            action='publish_release',phase='PUBLISH_RELEASE',status='QUEUED',attempts=0,events=[],created_at=int(service.clock()),
            release_id=rid,previous_release_id=env.get('active_release_id','initial'),previous_prefix=env.get('active_release_prefix',''))
        rows=[env,op,{'pk':ipk,'fingerprint':fp,'operation_id':oid}]
        service.store.commit(rows,expected(*rows));return service.store.get(op['pk'])
    return retry(transaction)


def publish(driver,env,op,before_switch=lambda:None):
    prefix='' if op['release_id']=='initial' else '.cloudhub/releases/'+op['release_id']+'/'
    bucket=driver._source(env);cfg=environment_configuration(env)
    if 'release_manifest' not in op:
        entries=objects(driver.s3,bucket,driver.settings,cfg,prefix=prefix)
        if not any(x['key']=='index.html' for x in entries):raise HubError('RELEASE_INCOMPLETE','The release needs index.html before activation.',409)
        # 100 small metadata entries remain well below the DynamoDB item limit.
        op['release_manifest']=entries;op['release_verify_cursor']=0
    cursor=int(op['release_verify_cursor'])
    for entry in op['release_manifest'][cursor:cursor+2]:
        data,meta=read(driver.s3,bucket,prefix+entry['key'],driver.settings['account_id'],limit=cfg['max_file_bytes'])
        expected=meta.get('Metadata',{}).get('sha256')
        if len(data)!=entry['size'] or (expected and sha(data)!=expected):raise HubError('RELEASE_DATA_MISMATCH','Release bytes do not match their uploaded checksums.',409)
        validate_links(data,meta.get('ContentType',''),entry['key'])
        entry['sha256']=sha(data)
        cursor+=1
    op['release_verify_cursor']=cursor
    if cursor<len(op['release_manifest']):return False
    # OriginPath must remain empty: versioned viewer URLs are rewritten by the
    # guard *before cache lookup*, independent of the currently active release.
    current=driver.cloudfront.get_distribution_config(Id=env['distribution_id'])
    config=current['DistributionConfig'];origin=next((o for o in config['Origins']['Items'] if o['Id']=='private-s3'),None)
    if not origin or origin.get('DomainName')!=bucket+'.s3.'+driver.settings['region']+'.amazonaws.com':
        raise HubError('RESOURCE_SCOPE_MISMATCH','The website origin does not match its owned bucket.',409)
    if origin.get('OriginPath',''):raise HubError('PUBLICATION_MIGRATION_REQUIRED','Legacy OriginPath publication needs a reviewed routing migration.',409)
    name='cloudhub-'+env['environment_id']+'-content'
    associations=config.get('DefaultCacheBehavior',{}).get('FunctionAssociations',{}).get('Items',[])
    if not any(a.get('EventType')=='viewer-request' and a.get('FunctionARN','').endswith(':function/'+name) for a in associations):
        raise HubError('PUBLICATION_MIGRATION_REQUIRED','The owned version-routing guard must be associated before publication.',409)
    previous_ids=env.get('published_release_ids',['initial'])
    published=sorted(set(previous_ids+[op['release_id']]))
    desired=routing_code(op['release_id'],published).encode()
    previous=routing_code(op['previous_release_id'],previous_ids).encode()
    live=driver.cloudfront.get_function(Name=name,Stage='LIVE');stream=live['FunctionCode']
    try:live_code=stream.read()
    finally:stream.close()
    if live_code!=desired:
        if live_code!=previous:raise HubError('PUBLICATION_CONFLICT','The live guard changed outside this operation; reconcile before proceeding.',409)
        development=driver.cloudfront.get_function(Name=name,Stage='DEVELOPMENT');stream=development['FunctionCode']
        try:development_code=stream.read()
        finally:stream.close()
        if development_code not in {previous,desired}:raise HubError('PUBLICATION_CONFLICT','Development guard has unrelated changes.',409)
        description=driver.cloudfront.describe_function(Name=name,Stage='DEVELOPMENT')
        if description['ETag']!=development['ETag']:return False
        function_config=description['FunctionSummary']['FunctionConfig']
        if function_config.get('Runtime')!='cloudfront-js-2.0':raise HubError('PUBLICATION_CONFLICT','Unexpected function runtime; reconcile configuration.',409)
        # Persist the attempt before either SDK call; uncertain responses reconcile
        # LIVE/DEVELOPMENT instead of creating endless updates or invalidations.
        attempts=int(op.get('cf_publish_attempts',0))
        if attempts>=3:raise HubError('PUBLICATION_RECONCILIATION_REQUIRED','Publication retry limit reached; retain all content and inspect the live guard.',409)
        op.update(cf_switch_attempted=True,cf_publish_attempts=attempts+1);before_switch()
        etag=development['ETag']
        if development_code!=desired:
            etag=driver.cloudfront.update_function(Name=name,IfMatch=etag,
                FunctionConfig=function_config,FunctionCode=desired)['ETag']
        driver.cloudfront.publish_function(Name=name,IfMatch=etag)
        return False
    deployed=driver.cloudfront.get_distribution(Id=env['distribution_id'])['Distribution']
    if deployed['Status']!='Deployed':return False
    domain=deployed['DomainName']
    if not re.fullmatch(r'[a-z0-9]+\.cloudfront\.net',domain):raise HubError('RESOURCE_SCOPE_MISMATCH','Invalid workload domain.',409)
    base='https://'+domain
    try:
        status,headers,_=driver.public_probe(base+'/',0)
        if status!=302 or headers.get('location')!=PUBLIC_PREFIX+op['release_id']+'/index.html':return False
        cursor=int(op.get('public_verify_cursor',0))
        for entry in op['release_manifest'][cursor:cursor+2]:
            status,_,data=driver.public_probe(base+PUBLIC_PREFIX+op['release_id']+'/'+entry['key'],cfg['max_file_bytes'])
            if status!=200 or sha(data)!=entry['sha256']:return False
            cursor+=1
        op['public_verify_cursor']=cursor
        if cursor<len(op['release_manifest']):return False
    except (OSError,TimeoutError):return False
    # This workload has its own distribution/origin, separate from the CloudHub UI.
    env.update(status='READY',needs_admin=False,publication_uncertain=False,previous_release_id=op['previous_release_id'],active_release_id=op['release_id'],active_release_prefix=prefix,published_release_ids=published)
    if env.get('draft_release_id')==op['release_id']:env['draft_release_id']=None
    op['result']={'release_id':op['release_id'],'data_verified':True,'infrastructure_verified':True,
                  'manifest_sha256':sha(json.dumps([{**entry,'size':int(entry['size'])} for entry in op['release_manifest']],sort_keys=True).encode()),
                  'rollback_release_id':op['previous_release_id'],'old_versions_retained':True,
                  'public_content_verified':True,'public_verification_scope':'Observer route only; not simultaneous verification of every CloudFront POP',
                  'versioned_url':base+PUBLIC_PREFIX+op['release_id']+'/index.html'}
    return True
