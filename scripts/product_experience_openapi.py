"""Reviewable application identity and human recovery/action metadata."""
def extend(doc):
    schemas=doc['components']['schemas'];ref=lambda n:{'$ref':'#/components/schemas/'+n}
    schemas['ReviewedApplication']={'type':'object','additionalProperties':False,'required':['release_id','title'],'properties':{
        'release_id':{'type':'string','enum':['content-site-1','content-site-2']},'revision':{'type':'string','pattern':'^[a-f0-9]{64}$'},
        'title':{'type':'string','minLength':1,'maxLength':80},'subtitle':{'type':'string','maxLength':240},
        'language':{'type':'string','enum':['vi','en','ja','ko','zh-Hans','fr','de','es']}},
        'description':'Bundled, operator-reviewed PostgreSQL content application. No arbitrary code/URL. Separately gated by template/configuration/Region/revision; preserves data schema 1. New stacks use reviewed compressed CFN parameters with UsePreviousTemplate updates; legacy environments are not silently migrated.'}
    for name,schema in schemas.items():
        if name in {'CreateRequest','EstimateRequest','Environment','RecoveryPoint'} or name.startswith('Create') or name.startswith('Estimate'):
            if schema.get('type')=='object' and 'properties' in schema:schema['properties']['application']=ref('ReviewedApplication')
    for path in ['/estimates','/environments']:
        body=doc['paths'].get(path,{}).get('post',{}).get('requestBody',{}).get('content',{}).get('application/json',{}).get('schema',{})
        if 'properties' in body:body['properties']['application']=ref('ReviewedApplication')
    schemas['ReviewedApplicationState']={**schemas['ReviewedApplication'],'required':['release_id','revision','title','subtitle','language','theme','data_schema'],
        'properties':{**schemas['ReviewedApplication']['properties'],'theme':{'type':'string','enum':['slate','indigo']},'data_schema':{'type':'integer','enum':[1]}}}
    for name in ['Environment','RecoveryPoint']:
        if name in schemas:schemas[name].setdefault('properties',{})['application']=ref('ReviewedApplicationState')
    schemas['ApplicationDeployment']={'type':'object','additionalProperties':False,'required':['application','expected_revision','expected_application_revision','confirmed'],'properties':{
        'application':ref('ReviewedApplication'),'expected_revision':{'type':'integer','minimum':0},'expected_application_revision':{'type':'string','pattern':'^[a-f0-9]{64}$'},'confirmed':{'type':'boolean','enum':[True]}}}
    doc['paths']['/environments/{environment_id}/application']={'post':{'operationId':'deployReviewedApplication','security':[{'CognitoAccessToken':[]}],
        'description':'Owner-only, revision-fenced, idempotent asynchronous release or rollback. Existing DB/data retained; brief interruption possible. No fresh environment, quota increase or arbitrary artifact. Native application gate required.',
        'parameters':[{'name':'environment_id','in':'path','required':True,'schema':{'type':'string'}},{'name':'Idempotency-Key','in':'header','required':True,'schema':{'type':'string','minLength':8,'maxLength':100}}],
        'requestBody':{'required':True,'content':{'application/json':{'schema':ref('ApplicationDeployment')}}},
        'responses':{'202':{'description':'Durable operation_id; not proof of readiness. Reconcile uncertain bootstrap or partial node outcomes.'},'403':{'description':'Owner/auth rejected'},'409':{'description':'Gate, revision, lock or legacy migration prevents deployment'}}}}
    if 'RecoveryPoint' in schemas:schemas['RecoveryPoint'].setdefault('properties',{})['action_availability']={'type':'object','description':'Read-only hints for restore/export/delete with allowed and reason; mutation APIs recheck ownership, status, expiry and locks. DELETE_FAILED blocks restore/export because partially deleted data is not a usable backup; safe delete retry may remain allowed.'}
    schemas['EnvironmentReadiness']={'type':'object','properties':{'operation_id':{'type':'string','nullable':True},'infrastructure_ready_at':{'type':'integer','nullable':True},'data_verified_at':{'type':'integer','nullable':True},'data_verification':{'type':'object','nullable':True}},'description':'Historical provisioning/restore proof, independent from the current management operation. Data verification is absent unless the restore worker actually checked the protected data; infrastructure readiness alone is not data proof or current availability.'}
    if 'Environment' in schemas:schemas['Environment'].setdefault('properties',{}).setdefault('detail',{'type':'object'}).setdefault('properties',{})['readiness']=ref('EnvironmentReadiness')
    doc['info']['description']+=' Planning uses exact decimal USD; legacy ledger reservations conservatively use integer milliUSD. Viewer geography does not change CloudFront PriceClass_100 or origin Region. Null prices/partial subtotals remain explicit.'
