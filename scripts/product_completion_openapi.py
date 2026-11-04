"""Current quote, continuous, direct-file and detail contracts."""
def extend(doc,operation,param):
    s=doc['components']['schemas'];paths=doc['paths']
    policy=s['OperatingPolicy']
    policy['properties']['mode']['enum']=['CONTINUOUS','AUTO_OFF','AUTO_RENEW']
    policy['properties']['period_minutes']={'type':'integer','nullable':True,'minimum':5,'maximum':480,
        'description':'null only for CONTINUOUS; no end deadline/schedule'}
    policy['oneOf'].append({'properties':{'mode':{'enum':['CONTINUOUS']},'period_minutes':{'nullable':True,'enum':[None]}}})
    if 'OperatingPolicyRead' in s:s['OperatingPolicyRead']['properties'].update(policy['properties'])
    policy['description']='CONTINUOUS is gated by administrator; ALERT_ONLY_PRESERVE_SOURCE at the forecast threshold. AUTO_RENEW remains opt-in.'
    for name in ['CreateInput','RenewInput','PolicyInput','LifecycleConsent']:
        if name not in s:continue
        s[name]['properties']['quote_id']={'type':'string','pattern':'^quote-[a-f0-9]{32}$'}
        s[name].setdefault('required',[]).append('quote_id')
    s['QuotedCommand']={'type':'object','additionalProperties':False,'required':['quote_id'],'properties':{'quote_id':{'type':'string','pattern':'^quote-[a-f0-9]{32}$'}}}
    for action in ['backup','destroy']:
        paths['/environments/{environment_id}/'+action]['post']['requestBody']['content']['application/json']['schema']={'$ref':'#/components/schemas/QuotedCommand'}
    s['TerminationConsent']={'type':'object','additionalProperties':False,'required':['quote_id','confirmed','expected_revision'],
        'properties':{'quote_id':{'type':'string','pattern':'^quote-[a-f0-9]{32}$'},'confirmed':{'type':'boolean','enum':[True]},'expected_revision':{'type':'integer','minimum':0}},
        'description':'Owner-bound 120-second data consent returned by management-estimate action end/destroy. No price-provider lookup or new budget reservation gates reduction. Mandatory backup and retention remain enforced; additional fees may be unpriced and journalled for reconciliation.'}
    for action in ['end','destroy']:
        op=paths['/environments/{environment_id}/'+action]['post']
        op['requestBody']['content']['application/json']['schema']={'$ref':'#/components/schemas/TerminationConsent'}
        op['description']='Review and explicitly confirm data policy/revision. Cost-reduction remains available when the budget is full or pricing is unavailable. Accepted identical idempotent retries return the original operation.'
    if 'ExtendInput' in s:
        s['ExtendInput']['properties']['quote_id']={'type':'string','pattern':'^quote-[a-f0-9]{32}$'}
        s['ExtendInput'].setdefault('required',[]).append('quote_id')
        legacy=paths['/environments/{environment_id}/extend']['post'];legacy['deprecated']=True
        legacy['description']='Use /renew. New requests require the matching renew quote; accepted legacy retries retain their operation.'
        legacy['responses']['202']=legacy['responses'].pop('200',{'description':'Accepted'})
    if 'deadline' in s.get('Environment',{}).get('properties',{}):s['Environment']['properties']['deadline']['nullable']=True
    for key in ['action','phase']:
        enum=s.get('Operation',{}).get('properties',{}).get(key,{}).get('enum')
        if enum is not None:enum.extend(x for x in (['commit_upload','publish_release'] if key=='action' else ['COMMIT_UPLOAD','PUBLISH_RELEASE']) if x not in enum)
    s['EstimateInput']['properties']['recovery_point']={'type':'string','pattern':'^rp-[a-f0-9]{24}$'}
    s['Quote']={'type':'object','required':['quote_id','quote_expires_at','price_version','currency'],
        'properties':{'quote_id':{'type':'string'},'quote_expires_at':{'type':'integer'},'price_version':{'type':'string'},'currency':{'type':'string','enum':['USD']}},'additionalProperties':True}
    s['UploadInput']={'type':'object','additionalProperties':False,'required':['key','size','sha256','content_type'],
        'properties':{'key':{'type':'string','maxLength':128},'size':{'type':'integer','minimum':1,'maximum':5242880},
            'sha256':{'type':'string','pattern':'^[a-f0-9]{64}$'},'content_type':{'type':'string'},
            'expected_version':{'type':'string'},'release_id':{'type':'string'}}}
    s['ReleaseInput']={'type':'object','additionalProperties':False,'required':['release_id','confirmed'],
        'properties':{'release_id':{'type':'string'},'confirmed':{'type':'boolean','enum':[True]}}}
    for suffix,opid,body,status,result in [
        ('uploads','initiateDirectUpload','UploadInput','200','Object'),
        ('uploads/{upload_id}/complete','completeDirectUpload','Empty','202','Operation'),
        ('uploads/{upload_id}/cancel','cancelPendingUpload','Empty','200','Object'),
        ('files/metadata','ownedFileMetadata','Object','200','Object'),
        ('releases','prepareWebsiteRelease','Empty','200','Object'),
        ('releases/activate','activateWebsiteRelease','ReleaseInput','202','Operation')]:
        params=[param('environment_id')]+([param('upload_id')] if '{upload_id}' in suffix else [])
        paths['/environments/{environment_id}/'+suffix]={'post':operation(opid,'post',body,params,status,result,True)}
    paths['/operations/{operation_id}/actions']={'get':operation('getOperationEligibility','get',None,[param('operation_id')])}
    paths['/environments/{environment_id}/uploads/{upload_id}/complete']['post']['description']='Owner-bound completion verifies exact size, type and SHA. Missing staged bytes return 409 UPLOAD_INCOMPLETE. S3 HEAD 403 is ambiguous without ListBucket and returns 409 UPLOAD_NOT_VISIBLE; this does not assert that a file exists or that permissions are correct. No operation is accepted in either case: retry the same upload/key or cancel, and contact the administrator if already transferred. Live data is preserved. The worker pins VersionId where available and always ETag plus SHA, including unversioned staging. Accepted replays return the same operation after gate closure.'
    s['FileList']['properties']['pending_upload']={'type':'object','nullable':True,'description':'Owned pending upload metadata only, for cancellation/recovery after reload; never contains a signed POST or AWS credentials.','properties':{'upload_id':{'type':'string'},'key':{'type':'string'},'status':{'type':'string'},'expires_at':{'type':'integer'},'complete_until':{'type':'integer'},'can_cancel':{'type':'boolean'}}}
    s['FileList']['properties']['legacy_inline_max_file_bytes']={'type':'integer','enum':[8192]}
    paths['/estimates']['post']['responses']['200']['content']['application/json']['schema']={'$ref':'#/components/schemas/Quote'}
    doc['info']['version']='0.8.0'
    paths['/environments/{environment_id}/releases/activate']['post']['description']='Checks source checksums, publishes a bounded CloudFront Function update and reconciles public redirect/content checksums. Stable root redirects with no-store to immutable /_cloudhub_site/{release}/ URLs. Local assets must use relative URLs; unpublished and internal paths are forbidden. Old published releases remain accessible; no global simultaneous-POP guarantee. An uncertain publication remains locked for reconciliation.'
    doc['info']['description']+=' Owner-bound single-use 120-second quotes are required for create/restore and manual renewal. 409 QUOTE_* requires explicit new review; accepted idempotent retries return the original operation even after expiry. Direct uploads and continuous mode default disabled until administrator review. Forecast ledger is not AWS billing.'
