"""Generate the exact per-template planning and evidence contracts."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from cloudhub.workloads import FIELDS

def extend(doc):
    schemas=doc['components']['schemas'];paths=doc['paths'];ref=lambda n:{'$ref':'#/components/schemas/'+n}
    policy={'type':'object','additionalProperties':False,'required':['mode','period_minutes','ending_policy','budget_limit_milliusd'],'properties':{
        'mode':{'type':'string','enum':['AUTO_OFF','AUTO_RENEW','CONTINUOUS']},'period_minutes':{'type':'integer','minimum':5,'maximum':480,'nullable':True},
        'ending_policy':{'type':'string','enum':['PAUSE','BACKUP_RETIRE']},'budget_limit_milliusd':{'type':'integer','minimum':1,'nullable':True}}}
    schemas['RecommendationPolicyInput']=policy
    variants=[];workload_refs=[]
    for tid,fields in FIELDS.items():
        fieldschema={}
        for f in fields:
            value={'type':'string' if f['type']=='enum' else 'integer','nullable':True,'description':f.get('unit','Published choice')+'; null means unknown.'}
            if f['type']=='enum':value['enum']=[*f['values'],None]
            else:value.update(minimum=f['minimum'],maximum=f['maximum'])
            fieldschema[f['key']]=value
        name='Workload'+tid;schemas[name]={'type':'object','additionalProperties':False,'properties':fieldschema};workload_refs.append(ref(name))
        properties={'template_id':{'type':'string','enum':[tid]},'mode':{'type':'string','enum':['RECOMMEND','ASSESS']},'region':{'type':'string','enum':['ap-southeast-1','ap-northeast-1','us-east-1']},
            'estimate_hours':{'type':'integer','enum':[1,2,4,8]},'budget_milliusd':{'type':'integer','minimum':0,'maximum':10**9,'nullable':True},
            'profile_id':{'type':'string','enum':['standard','expanded','files']},'workload':ref(name),'operating_policy':ref('RecommendationPolicyInput'),
            'application_revision':{'type':'string','pattern':'^[a-f0-9]{64}$','nullable':True},'scenario_revision':{'type':'string','pattern':'^[a-f0-9]{64}$','nullable':True}}
        variants.append({'type':'object','additionalProperties':False,'required':['template_id','mode','region','estimate_hours','workload'],'properties':properties,
            'description':'ASSESS additionally requires profile_id. Explicit purpose maps to this template. No target URL, owner, price or verified flag accepted.'})
    schemas['RecommendationInput']={'oneOf':variants}
    schemas['PlanningWorkload']={'anyOf':workload_refs,'description':'Validated against the enclosing template_id. Same normalized workload is bound into quote, environment, renewals and forecast ledger; no amount is trusted from the client.'}
    schemas['RecommendationResult']={'type':'object','required':['schema','template_id','region','demand','options','assessment','is_quote','read_only','status'],'properties':{
        'schema':{'type':'string','enum':['workload-1']},'template_id':{'type':'string'},'region':{'type':'string'},'read_only':{'type':'boolean','enum':[True]},'is_quote':{'type':'boolean','enum':[False]},
        'admission_checked':{'type':'boolean','enum':[False]},'status':{'type':'string','enum':['OPTIONS','NO_MATCH']},'demand':{'type':'object','additionalProperties':{'type':'string','nullable':True}},
        'options':{'type':'array','items':ref('RecommendationOption')},'assessment':{'type':'object','nullable':True,'additionalProperties':True},'excluded':{'type':'array','items':{'type':'object','additionalProperties':True}}}}
    schemas['RecommendationOption']={'type':'object','required':['configuration','region','profile_id','status','cost','capacity','evidence_level','can_select','creation_defaults'],'properties':{
        'configuration':{'type':'object'},'region':{'type':'string'},'profile_id':{'type':'string'},'status':{'type':'string'},'cost':ref('Estimate'),
        'capacity':{'type':'object','nullable':True,'description':'Observed metrics only, null without matching published evidence. Numeric measurements use decimal strings; benchmark.rate_unit distinguishes request/job/I/O/transfer. Not visitors or global capacity.'},
        'evidence_level':{'type':'string','enum':['APPLICATION_VERIFIED','SAMPLE_APPLICATION','RESOURCE_REQUIREMENTS','INSUFFICIENT_DATA']},'benchmark':{'type':'object','nullable':True},
        'can_select':{'type':'boolean'},'creation_defaults':{'type':'object','description':'Form defaults only. A new authenticated quote and explicit confirmation/quota/idempotency are still mandatory.'},
        'budget_status':{'type':'string','enum':['UNKNOWN','NOT_SET','WITHIN','EXCEEDED']}}}
    schemas['BenchmarkReport']={'type':'object','additionalProperties':False,'required':['schema','template_id','region','configuration','capability_revision','application','scenario','workload','infrastructure','generator','execution','samples','observations','bottlenecks','evidence_files'],'properties':{
        'schema':{'type':'integer','enum':[1]},'template_id':{'type':'string','enum':sorted(FIELDS)},'region':{'type':'string'},'configuration':{'type':'object'},
        'capability_revision':{'type':'string','pattern':'^[a-f0-9]{64}$'},'application':{'type':'object'},'scenario':{'type':'object'},'workload':ref('PlanningWorkload'),
        **{key:{'type':'object'} for key in ['infrastructure','generator','execution','observations']},
        'samples':{'type':'array','minItems':1,'maxItems':10000,'items':{'type':'object','additionalProperties':False,'required':['elapsed_ms','ok','bytes','correct'],'properties':{
            'elapsed_ms':{'type':'number','minimum':0},'ok':{'type':'boolean'},'bytes':{'type':'integer','minimum':0},'correct':{'type':'boolean'}}}},
        'bottlenecks':{'type':'array','minItems':1,'items':{'type':'string'}},'evidence_files':{'type':'array','minItems':1,'maxItems':3,'items':{'type':'object','required':['name','sha256'],'properties':{'name':{'type':'string'},'sha256':{'type':'string','pattern':'^[a-f0-9]{64}$'}}}}}}
    for name in ['CreateInput','EstimateInput']:
        if name in schemas:schemas[name].setdefault('properties',{})['planning_workload']=ref('PlanningWorkload')
    for path in ['/estimates','/environments']:
        body=paths.get(path,{}).get('post',{}).get('requestBody',{}).get('content',{}).get('application/json',{}).get('schema',{})
        if 'properties' in body:body['properties']['planning_workload']=ref('PlanningWorkload')
    def operation(method,output,body=None,admin=False):
        value={'tags':['F03 configuration recommendations' if not admin else 'Administrator benchmark evidence'],
            'security':[{'CognitoAccessToken':[]}],'responses':{str(n):{'description':text,'content':{'application/json':{'schema':output if n==200 else ref('Error')}}} for n,text in [(200,'Successful read or evidence metadata update'),(400,'Invalid template workload or incomplete evidence'),(401,'Cognito authentication required'),(403,'Verified account / administrator required'),(409,'Capability, quote or source changed'),(429,'Route throttled'),(503,'Reviewed prices or private evidence unavailable')]}}
        if body:value['requestBody']={'required':True,'content':{'application/json':{'schema':body}}}
        return value
    paths['/recommendations']={'post':operation('POST',ref('RecommendationResult'),ref('RecommendationInput'))}
    paths['/recommendations/schema']={'get':operation('GET',{'type':'object','description':'Per-template nullable fields, explicit example demand, Region/configuration gates and operator policy. Examples are never benchmarks.'})}
    digest={'type':'string','pattern':'^[a-f0-9]{64}$'}
    paths['/admin/benchmarks']={'get':operation('GET',{'type':'object'},admin=True),'post':operation('POST',{'type':'object'},{'type':'object','additionalProperties':False,'required':['evidence_sha256'],'properties':{'evidence_sha256':digest}},True)}
    paths['/admin/benchmarks/{benchmark_id}/{control}']={'parameters':[{'name':'benchmark_id','in':'path','required':True,'schema':{'type':'string','pattern':'^bench-[a-f0-9]{24}$'}},{'name':'control','in':'path','required':True,'schema':{'type':'string','enum':['publish','retire']}}],
        'post':operation('POST',{'type':'object'},{'type':'object','additionalProperties':False,'required':['evidence_sha256','reviewed'],'properties':{'evidence_sha256':digest,'reviewed':{'type':'boolean','enum':[True]}}},True)}
