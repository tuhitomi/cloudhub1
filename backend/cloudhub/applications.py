"""Versioned operator-reviewed applications on the existing EC2/PostgreSQL stack.

No client code/image/URL or arbitrary artifact is accepted. Native gates are
separate from the historical T03/T04 infrastructure proof and default closed.
"""
import hashlib,json,re,gzip,base64
from pathlib import Path
from .errors import HubError
RELEASES={'content-site-1':{'theme':'slate','data_schema':1},'content-site-2':{'theme':'indigo','data_schema':1}}

def revision(release):
    if not isinstance(release,str) or release not in RELEASES:raise HubError('APPLICATION_INVALID','Choose an operator-reviewed application release.')
    source=Path(__file__).with_name('content_app.py').read_bytes()+Path(__file__).with_name('rds_app.py').read_bytes()
    return hashlib.sha256(source+json.dumps(RELEASES[release],sort_keys=True).encode()).hexdigest()

def normalize(value):
    if not isinstance(value,dict) or set(value)-{'release_id','title','subtitle','language','revision'} or not {'release_id','title'}<=value.keys():raise HubError('APPLICATION_INVALID','Use the reviewed application contract.')
    release=value['release_id'];digest=revision(release)
    if value.get('revision',digest)!=digest:raise HubError('APPLICATION_CHANGED','Application artifact changed; review the current release.',409)
    for key,limit in [('title',80),('subtitle',240)]:
        text=value.get(key,'')
        if not isinstance(text,str) or (key=='title' and not text.strip()) or len(text)>limit or any(ord(c)<32 for c in text):raise HubError('APPLICATION_INVALID','Use plain bounded text.',details={'field':key})
    language=value.get('language','en')
    if language not in {'vi','en','ja','ko','zh-Hans','fr','de','es'}:raise HubError('APPLICATION_INVALID','Choose a supported language.')
    return {'release_id':release,'revision':digest,'title':value['title'].strip(),'subtitle':value.get('subtitle',''),'language':language,**RELEASES[release]}

def request_value(value):return {k:value[k] for k in ['release_id','revision','title','subtitle','language']}

def configuration_json(value):
    """DynamoDB persists schema numbers as Decimal; validate and emit JSON ints."""
    return json.dumps(normalize(request_value(value)),ensure_ascii=False,sort_keys=True)

def deployment_parameters(value):
    """Reviewed payloads fit CFN's 4096-byte parameter limit; no new IAM read."""
    app=Path(__file__).with_name('rds_app.py').read_bytes();content=Path(__file__).with_name('content_app.py').read_bytes()
    result={'CloudHubApplicationConfig':base64.b64encode(configuration_json(value).encode()).decode(),
        'CloudHubApplicationCode':base64.b64encode(gzip.compress(app,mtime=0)).decode(),
        'CloudHubContentCode':base64.b64encode(gzip.compress(content,mtime=0)).decode(),
        'CloudHubApplicationCodeSha256':hashlib.sha256(app).hexdigest(),'CloudHubContentCodeSha256':hashlib.sha256(content).hexdigest()}
    if any(len(v.encode())>4096 for v in result.values()):raise HubError('APPLICATION_ARTIFACT_LIMIT','Reviewed artifact exceeds the CloudFormation parameter contract; no deployment attempted.',409)
    return result

def available(service,tid,region,release,configuration=None):
    if tid not in {'T03','T04'}:return False
    from .catalog import configuration_key,resolve_configuration
    proof=service.regions_config.get('application_releases',{}).get(region,{}).get(tid,{}).get(release,{})
    return (proof.get('passed') is True and proof.get('revision')==revision(release) and proof.get('data_verified') is True and proof.get('rollback_verified') is True
        and configuration_key(tid,resolve_configuration(tid,configuration)) in proof.get('configuration_keys',[]))

def options(service,tid,region):
    if tid not in {'T03','T04'}:return []
    from .catalog import configuration_profiles
    supported=lambda r:[p['id'] for p in configuration_profiles(tid) if available(service,tid,region,r,p['configuration'])]
    return [{'release_id':r,'revision':revision(r),'configuration_ids':supported(r),'enabled':bool(supported(r)),'status':'SUPPORTED' if supported(r) else 'VERIFYING',
        'data_schema':1,'source':'BUNDLED_OPERATOR_REVIEWED','limits':{'public_mutations':False,'arbitrary_code':False,'managed_records':32,'managed_record_bytes':256},
        'backup_scope':'RDS snapshot + record SHA; application identity/config in recovery metadata. EC2 root and logs are excluded.'} for r in RELEASES]

def validate_create(service,tid,region,body,permitted_validation):
    value=body.get('application')
    if value is None:return None
    app=normalize(value)
    if tid not in {'T03','T04'}:raise HubError('APPLICATION_UNSUPPORTED','Only T03/T04 support this reviewed application.',409)
    if not available(service,tid,region,app['release_id'],body.get('configuration')) and not permitted_validation:raise HubError('APPLICATION_UNVERIFIED','Application release has not passed native validation for this template, configuration and Region.',409)
    return app

def restore_inputs(service,owner,body):
    source=service.owned('R',body['recovery_point'],owner)
    if not source.get('application'):
        if body.get('application'):raise HubError('APPLICATION_LEGACY_MIGRATION_REQUIRED','Legacy backup has no application identity; no silent migration.',409)
        return body
    expected=source['application'];requested=normalize(body['application']) if body.get('application') else expected
    if requested!=expected:raise HubError('APPLICATION_RESTORE_MISMATCH','Restore keeps the saved application release and configuration.',409)
    return {**body,'application':request_value(expected)}

def begin(service,owner,eid,key,body,is_admin=False):
    from .service import retry
    if not isinstance(body,dict) or set(body)!={'application','expected_revision','expected_application_revision','confirmed'} or body['confirmed'] is not True:raise HubError('APPLICATION_CONSENT_REQUIRED','Confirm the release, restart window and unchanged database scope.')
    def transaction():
        env=service.owned('E',eid,owner);_,_,old=service.idempotency(owner,key,eid+'/deploy_application',body)
        if old:return service.owned('O',old['operation_id'],owner)
        service._assert_mutable(env,body,states={'READY','ERROR_RETAINED'})
        from .quotes import fingerprint
        if body['expected_application_revision']!=fingerprint(env.get('application')):raise HubError('APPLICATION_CHANGED','Application configuration changed; review it again.',409)
        app=normalize(body['application'])
        validation=is_admin and env.get('validation_run') is True and env['template_id'] in service.validation
        from .catalog import environment_configuration
        if not available(service,env['template_id'],service.region_for(env),app['release_id'],environment_configuration(env)) and not validation:raise HubError('APPLICATION_UNVERIFIED','This release is not enabled for the environment configuration.',409)
        if not env.get('application'):raise HubError('APPLICATION_LEGACY_MIGRATION_REQUIRED','Existing demo environments require a separate migration; source is preserved.',409)
        env['application_pending']=app
        return service._management(env,key,'deploy_application',body,'DEPLOY_APPLICATION',fields={'application_target':app,'application_previous':env['application'],
            'application_step':'UPDATE_BOOTSTRAP','data_schema':1,'cost_scope':'No new infrastructure; existing environment remains billable; deployment may briefly interrupt requests.'})
    return retry(transaction)
