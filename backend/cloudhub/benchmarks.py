"""Immutable S3 evidence, owner-indexed metadata, administrator publication.

No load generator is invoked by the API. Reading suggestions never creates a
benchmark, operation, quote, reservation or user resource.
"""
import hashlib,json,os,re,math
from decimal import Decimal
from .catalog import ACTIVE_TEMPLATES,configuration_key,resolve_configuration
from .errors import HubError
from .quotes import fingerprint
from .service import expected,retry
from .workloads import VERSION,normalize

OWNER='__cloudhub_benchmark_registry__'
MAX_BYTES=2*1024*1024
SHA=re.compile(r'^[a-f0-9]{64}$')

def capability_revision(tid,cfg):
    from pathlib import Path
    files={'T01':['templates.py'],'T02':['s3_template.py'],'T03':['rds_template.py','rds_app.py'],
        'T04':['rds_template.py','rds_app.py'],'T05':['templates.py'],'T06':['ecs_template.py'],
        'T07':['s3_template.py'],'T08':['efs_template.py','efs_records.py'],'T09':['data_template.py','data_api_app.py']}[tid]
    return fingerprint({'schema':VERSION,'template_id':tid,'configuration':resolve_configuration(tid,cfg),
        'template_sources':{name:hashlib.sha256(Path(__file__).with_name(name).read_text(encoding='utf-8').encode()).hexdigest() for name in files}})

def policy(service):
    try:raw=json.loads(os.getenv('RECOMMENDATION_POLICY_JSON','{}'))
    except (ValueError,TypeError):raise HubError('RECOMMENDATION_POLICY_INVALID','Review the operator recommendation policy.',503)
    if not isinstance(raw,dict):raise HubError('RECOMMENDATION_POLICY_INVALID','Policy must be an object.',503)
    if set(raw)-{'schema','resource_headroom_percent','max_benchmark_age_days','observed_quotas'}:
        raise HubError('RECOMMENDATION_POLICY_INVALID','Review the operator recommendation policy.',503)
    value={'schema':1,'resource_headroom_percent':0,'max_benchmark_age_days':30,'observed_quotas':{},**raw}
    if type(value['schema']) is not int or value['schema']!=1 or not isinstance(value['observed_quotas'],dict):raise HubError('RECOMMENDATION_POLICY_INVALID','Invalid policy schema/quotas.',503)
    ceiling=value['observed_quotas'].get('lambda_account_concurrency')
    if ceiling is not None and (type(ceiling) is not int or ceiling<1 or not value['observed_quotas'].get('observed_at')):raise HubError('RECOMMENDATION_POLICY_INVALID','Quota observations require a timestamp and positive integer.',503)
    for key,low,high in [('resource_headroom_percent',0,100),('max_benchmark_age_days',1,365)]:
        if type(value[key]) is not int or not low<=value[key]<=high:raise HubError('RECOMMENDATION_POLICY_INVALID','Invalid operator policy.',503)
    return value

def _safe_json(value):
    if isinstance(value,dict):
        for key,item in value.items():
            if re.search(r'password|access.?token|refresh.?token|authorization|cookie|private.?key|access.?key|session.?token|client.?secret|secret.?string|secret.?value|credential',key,re.I):
                raise HubError('BENCHMARK_SENSITIVE','Remove credentials and authentication material from evidence.')
            _safe_json(item)
    elif isinstance(value,list):
        for item in value:_safe_json(item)
    elif isinstance(value,str) and ('X-Amz-Signature=' in value or re.search(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',value)):
        raise HubError('BENCHMARK_SENSITIVE','Remove signed URLs or credentials from evidence.')
    elif isinstance(value,float) and not math.isfinite(value):raise HubError('BENCHMARK_INVALID','Non-finite measurements are invalid.')

def summarize(samples,duration_s):
    if not isinstance(samples,list) or not 1<=len(samples)<=10000:raise HubError('BENCHMARK_INCOMPLETE','Supply 1–10000 raw observations.')
    times=[];errors=0;size=Decimal(0)
    for item in samples:
        if not isinstance(item,dict) or set(item)!={'elapsed_ms','ok','bytes','correct'}:raise HubError('BENCHMARK_INCOMPLETE','Invalid raw observation.')
        try:value=Decimal(str(item['elapsed_ms']))
        except Exception:raise HubError('BENCHMARK_INCOMPLETE','Invalid latency.')
        if not value.is_finite() or value<0 or type(item['ok']) is not bool or type(item['correct']) is not bool or type(item['bytes']) is not int or item['bytes']<0:raise HubError('BENCHMARK_INCOMPLETE','Invalid observation values.')
        times.append(value);errors+=not(item['ok'] and item['correct']);size+=item['bytes'] if item['ok'] and item['correct'] else 0
    times.sort();count=len(times)
    return {'attempts':count,'errors':errors,'error_rate':str(Decimal(errors)/count),'p50_ms':str(times[math.ceil(count*.5)-1]),
        'p95_ms':str(times[math.ceil(count*.95)-1]),'max_ms':str(times[-1]),'achieved_operations_per_second':str(Decimal(count)/Decimal(duration_s)),
        'successful_operations_per_second':str(Decimal(count-errors)/Decimal(duration_s)),
        'successful_mib_per_second':str(size/1048576/Decimal(duration_s)),'correctness_checked':True}

def validate_report(service,value,*,allow_fixture=False):
    required={'schema','template_id','region','configuration','capability_revision','application','scenario','workload','infrastructure',
        'generator','execution','samples','observations','bottlenecks','evidence_files'}
    if not isinstance(value,dict) or set(value)!=required or value['schema']!=1:raise HubError('BENCHMARK_INCOMPLETE','Use the complete benchmark contract; verified flags are not accepted.')
    _safe_json(value);tid=value['template_id'];cfg=resolve_configuration(tid,value['configuration']) if tid in ACTIVE_TEMPLATES else None
    if cfg is None:raise HubError('TEMPLATE_UNAVAILABLE','Choose T01–T09.',409)
    region=service.region_registry().select(value['region']);workload=normalize(tid,value['workload'])
    if value['capability_revision']!=capability_revision(tid,cfg):raise HubError('BENCHMARK_STALE','Configuration contract changed.',409)
    execution=value['execution'];app=value['application'];scenario=value['scenario']
    if not isinstance(execution,dict) or not {'mode','environment_id','started_at','ended_at','duration_s','warmup_s','target_rate','rate_unit','dropped_iterations','stop_reason'}<=execution.keys():raise HubError('BENCHMARK_INCOMPLETE','Execution provenance is missing.')
    if execution['mode']!='AWS_ISOLATED_TEST' and not (allow_fixture and execution['mode']=='LOCAL_FIXTURE'):
        raise HubError('BENCHMARK_FIXTURE_REJECTED','Only isolated AWS measurements can be published.')
    for key in ['started_at','ended_at','duration_s','warmup_s','dropped_iterations']:
        if type(execution[key]) is not int or execution[key]<0:raise HubError('BENCHMARK_INCOMPLETE','Invalid execution timing/rate.')
    try:target=Decimal(str(execution['target_rate']))
    except Exception:raise HubError('BENCHMARK_INCOMPLETE','Invalid target arrival rate.')
    if isinstance(execution['target_rate'],bool) or not target.is_finite() or target<=0:raise HubError('BENCHMARK_INCOMPLETE','Target arrival rate must be positive and finite.')
    if not 1<=execution['duration_s']<=3600 or execution['warmup_s']>execution['duration_s'] or execution['ended_at']-execution['started_at']!=execution['duration_s'] or execution['ended_at']>int(service.clock())+60:
        raise HubError('BENCHMARK_INCOMPLETE','Measurement timing is inconsistent.')
    if execution['rate_unit'] not in {'requests/s','jobs/s','operations/s','transfers/s'} or execution['stop_reason'] not in {'COMPLETED','ERROR_BUDGET','GENERATOR_LIMIT','TIME_LIMIT'}:raise HubError('BENCHMARK_INCOMPLETE','Declare the generator model and stop condition.')
    if not isinstance(app,dict) or set(app)!={'kind','revision','dataset_revision'} or app['kind'] not in {'SAMPLE','OWNED_APPLICATION'} or not all(isinstance(app[k],str) and SHA.fullmatch(app[k]) for k in ['revision','dataset_revision']):raise HubError('BENCHMARK_INCOMPLETE','Bind application and dataset revisions.')
    if not isinstance(scenario,dict) or set(scenario)!={'id','revision','workload_schema'} or not isinstance(scenario['id'],str) or not re.fullmatch('[a-z0-9-]{1,80}',scenario['id']) or not SHA.fullmatch(str(scenario['revision'])) or scenario['workload_schema']!=VERSION:raise HubError('BENCHMARK_INCOMPLETE','Bind the scenario revision.')
    for name,required_keys in [('infrastructure',{'configuration','limits','quota_snapshot','application_artifact'}),('generator',{'location','tool','version','cpu','memory_mib','model','max_concurrency'}),('observations',{'cpu_credits_before','cpu_credits_after','cloudwatch','scaling_timeline','cache_state','data_correctness'})]:
        if not isinstance(value[name],dict) or not required_keys<=value[name].keys():raise HubError('BENCHMARK_INCOMPLETE','Incomplete '+name+'.')
    generator=value['generator']
    if any(not isinstance(generator[k],str) or not 1<=len(generator[k])<=200 for k in ['location','tool','version']) or any(type(generator[k]) is not int or generator[k]<1 for k in ['cpu','memory_mib','max_concurrency']) or generator['model']!='arrival-rate':raise HubError('BENCHMARK_INCOMPLETE','Declare generator resources and arrival-rate model.')
    if not isinstance(value['infrastructure']['limits'],dict) or len(json.dumps(value['infrastructure']['limits']))>100000:raise HubError('BENCHMARK_TOO_LARGE','Keep bounded metadata; detailed observations belong in private S3 evidence.')
    if value['infrastructure']['configuration']!=cfg or value['observations']['data_correctness'] is not True:raise HubError('BENCHMARK_INCOMPLETE','Infrastructure/correctness evidence must match.')
    if tid in {'T01','T03','T04','T05','T08'} and any(value['observations'][k] is None for k in ['cpu_credits_before','cpu_credits_after']):raise HubError('BENCHMARK_INCOMPLETE','Record EC2 credit state before and after the measurement.')
    if tid=='T04' and not value['observations']['scaling_timeline']:raise HubError('BENCHMARK_INCOMPLETE','Record steady/ramp/scale-out and shared database observations.')
    if not allow_fixture:
        observations=value['observations']
        if tid in {'T01','T03','T04','T05','T08'}:
            nodes=[r['id'] for r in value['infrastructure']['limits'].get('inventory',[]) if r.get('type')=='AWS::EC2::Instance']
            if not nodes or any(not observations[side].get(node+'/CPUCreditBalance') for side in ['cpu_credits_before','cpu_credits_after'] for node in nodes):raise HubError('BENCHMARK_INCOMPLETE','CloudWatch CPU-credit datapoints are required for every burstable instance; wait for delayed metrics.')
        if tid=='T04':
            phases={p.get('phase') for p in observations['scaling_timeline']}
            db=observations['cloudwatch'].get('after',{})
            if not {'STEADY','RAMP','SCALE_OUT'}<=phases or not any(k.endswith('/DatabaseConnections') and v for k,v in db.items()):raise HubError('BENCHMARK_INCOMPLETE','Actual scale-out and shared DB datapoints must be observed, not inferred from ASG limits.')
        if tid=='T08' and observations.get('cross_node_correctness') is not True:raise HubError('BENCHMARK_INCOMPLETE','Both EFS clients must read each other’s checksum-verified marker.')
    if tid=='T02' and value['observations']['cache_state'] not in {'COLD','WARM','MIXED'}:raise HubError('BENCHMARK_INCOMPLETE','Declare CloudFront cache state and geographic limits.')
    if tid=='T02' and not allow_fixture:
        from .benchmark_agent import classify_cache
        states=value['observations'].get('cache_observations')
        if not isinstance(states,list) or not states or any(not isinstance(v,dict) for v in states) or classify_cache(states)!=value['observations']['cache_state']:raise HubError('BENCHMARK_INCOMPLETE','Cache classification must match observed CloudFront response headers; unknown is not warm/mixed.')
    if not isinstance(value['bottlenecks'],list) or not value['bottlenecks'] or not isinstance(value['evidence_files'],list) or not value['evidence_files']:raise HubError('BENCHMARK_INCOMPLETE','Supply observations and evidence file hashes.')
    for item in value['evidence_files']:
        if not isinstance(item,dict) or set(item)!={'name','sha256'} or not re.fullmatch('[A-Za-z0-9_.-]{1,100}',str(item['name'])) or not SHA.fullmatch(str(item['sha256'])):raise HubError('BENCHMARK_INCOMPLETE','Evidence must have safe names and SHA-256 digests.')
    if len(value['evidence_files'])>3:raise HubError('BENCHMARK_TOO_LARGE','At most three raw source files are accepted.')
    if not allow_fixture:
        env=service.store.get('E#'+str(execution['environment_id']))
        if not env or env.get('validation_run') is not True or env['template_id']!=tid or service.region_for(env)!=region or resolve_configuration(tid,env.get('configuration'))!=cfg:
            raise HubError('BENCHMARK_TARGET_FORBIDDEN','Evidence must refer to a CloudHub isolated validation environment.',403)
        if app['kind']=='OWNED_APPLICATION' and (not env.get('application_revision') or env['application_revision']!=app['revision']):raise HubError('BENCHMARK_APPLICATION_UNVERIFIED','Application identity is not recorded by CloudHub.',409)
    metrics=summarize(value['samples'],execution['duration_s'])
    actual=Decimal(metrics['achieved_operations_per_second'])
    generator_limited=execution['dropped_iterations']>0 or actual<target or execution['stop_reason']!='COMPLETED'
    return {'schema':1,'template_id':tid,'region':region,'configuration':cfg,'configuration_key':configuration_key(tid,cfg),
        'capability_revision':value['capability_revision'],'application':app,'scenario':scenario,'workload':workload,
        'workload_fingerprint':fingerprint(workload),'measured_at':execution['ended_at'],'metrics':metrics,
        'generator_limited':bool(generator_limited),'target_rate':str(target),'rate_unit':execution['rate_unit'],
        'duration_s':execution['duration_s'],'warmup_s':execution['warmup_s'],'bottlenecks':value['bottlenecks'],
        'test_environment_id':execution['environment_id'],'test_owner':env['owner_id'] if not allow_fixture else 'LOCAL_ONLY',
        'limits':json.loads(json.dumps(value['infrastructure']['limits'],allow_nan=False),parse_float=Decimal),'measurement_scope':value['observations'].get('measurement_scope','Recorded reference workload only; inspect source evidence.'),'generator_location':value['generator']['location'],'cache_state':value['observations']['cache_state']}

def load_evidence(digest):
    if not isinstance(digest,str) or not SHA.fullmatch(digest):raise HubError('BENCHMARK_INVALID','Use an evidence SHA-256 digest.')
    bucket=os.getenv('BENCHMARK_BUCKET','')
    if not bucket:raise HubError('BENCHMARK_STORAGE_UNCONFIGURED','Operator must configure the existing private evidence bucket.',503)
    import boto3
    from botocore.config import Config
    client=boto3.client('s3',config=Config(connect_timeout=1,read_timeout=3,retries={'total_max_attempts':1}))
    key='benchmarks/v1/'+digest+'/report.json'
    try:
        response=client.get_object(Bucket=bucket,Key=key)
        if response['ContentLength']>MAX_BYTES:raise HubError('BENCHMARK_TOO_LARGE','Evidence exceeds 2 MiB.')
        blob=response['Body'].read(MAX_BYTES+1)
    except HubError:raise
    except Exception:raise HubError('BENCHMARK_EVIDENCE_UNAVAILABLE','The private evidence object cannot be read.',503)
    if len(blob)>MAX_BYTES or hashlib.sha256(blob).hexdigest()!=digest:raise HubError('BENCHMARK_DIGEST_MISMATCH','Evidence does not match its content digest.',409)
    try:value=json.loads(blob)
    except (ValueError,UnicodeError):raise HubError('BENCHMARK_INVALID','Invalid evidence JSON.')
    files=value.get('evidence_files',[]) if isinstance(value,dict) else []
    if not 1<=len(files)<=3:raise HubError('BENCHMARK_INCOMPLETE','Supply bounded raw evidence files.')
    total=len(blob)
    for item in files:
        name=item.get('name') if isinstance(item,dict) else None
        if not isinstance(name,str) or not re.fullmatch('[A-Za-z0-9_.-]{1,100}',name) or not SHA.fullmatch(str(item.get('sha256'))):raise HubError('BENCHMARK_INVALID','Unsafe evidence reference.')
        try:
            source=client.get_object(Bucket=bucket,Key='benchmarks/v1/'+digest+'/evidence/'+name)
            if source['ContentLength']>MAX_BYTES:raise HubError('BENCHMARK_TOO_LARGE','Raw evidence exceeds bounds.')
            data=source['Body'].read(MAX_BYTES+1);total+=len(data)
        except HubError:raise
        except Exception:raise HubError('BENCHMARK_EVIDENCE_UNAVAILABLE','A private raw source file cannot be read.',503)
        if len(data)>MAX_BYTES or total>MAX_BYTES*2 or hashlib.sha256(data).hexdigest()!=item['sha256']:raise HubError('BENCHMARK_DIGEST_MISMATCH','Raw evidence digest or size mismatch.',409)
        if name.endswith('.json'):
            try:raw=json.loads(data)
            except (ValueError,UnicodeError):raise HubError('BENCHMARK_INVALID','Invalid raw evidence JSON.')
            _safe_json(raw)
            if name=='raw-observations.json' and raw!=value.get('samples'):raise HubError('BENCHMARK_DIGEST_MISMATCH','Report observations differ from the immutable raw source.',409)
    if not any(v['name']=='raw-observations.json' for v in files):raise HubError('BENCHMARK_INCOMPLETE','Include the raw-observations.json source used to recompute metrics.')
    return value

def admin_route(service,method,path,body,owner,admin,loader=load_evidence):
    if not (path=='/admin/benchmarks' or re.fullmatch('/admin/benchmarks/bench-[a-f0-9]{24}/(publish|retire)',path)):return None
    if not admin:raise HubError('FORBIDDEN','Administrator access is required.',403)
    if path=='/admin/benchmarks' and method=='GET':
        return {'items':[{k:v for k,v in r.items() if k not in {'pk','owner_id','owner_sort','version','test_owner','test_environment_id'}} for r in service.store.list_owner(OWNER,'benchmark')]}
    if path=='/admin/benchmarks' and method=='POST':
        if set(body)!={'evidence_sha256'}:raise HubError('BENCHMARK_INVALID','Import a content-addressed evidence object, not client verification flags.')
        digest=body['evidence_sha256'];value=validate_report(service,loader(digest));bid='bench-'+digest[:24]
        def commit():
            old=service.store.get('B#'+bid)
            if old:
                if old['evidence_sha256']!=digest:raise HubError('BENCHMARK_CONFLICT','Benchmark ID collision.',409)
                return {'benchmark_id':bid,'status':old['status']}
            row={**value,'pk':'B#'+bid,'kind':'benchmark','owner_id':OWNER,'owner_sort':'benchmark#'+bid,'benchmark_id':bid,
                'evidence_sha256':digest,'status':'DRAFT','imported_at':int(service.clock()),'imported_by':owner,'publication_history':[]}
            service.store.commit([row],{row['pk']:None});return {'benchmark_id':bid,'status':'DRAFT'}
        return retry(commit)
    if method=='POST' and path!='/admin/benchmarks':
        if set(body)!={'evidence_sha256','reviewed'} or body['reviewed'] is not True:raise HubError('BENCHMARK_REVIEW_REQUIRED','Review the immutable source, correctness, generator limits and application scope.')
        bid=path.split('/')[3];action=path.split('/')[4]
        def commit():
            row=service.store.get('B#'+bid)
            if not row:raise HubError('NOT_FOUND','Benchmark not found.',404)
            if row['evidence_sha256']!=body['evidence_sha256']:raise HubError('BENCHMARK_CONFLICT','Review the current evidence digest.',409)
            if action=='publish':validate_report(service,loader(row['evidence_sha256']))
            target='PUBLISHED' if action=='publish' else 'RETIRED'
            if row['status']!=target:
                row['status']=target;row['publication_history'].append({'status':target,'at':int(service.clock()),'actor':owner})
                service.store.commit([row],expected(row))
            return {'benchmark_id':bid,'status':target}
        return retry(commit)
    raise HubError('NOT_FOUND','Unsupported benchmark route.',404)

def matching(service,owner,tid,region,cfg,workload,application_revision=None,scenario_revision=None):
    p=policy(service);found=[];excluded=[]
    for candidate in service.store.list_owner(OWNER,'benchmark'):
        # The GSI is eventually consistent: re-read the authoritative status so a
        # retired publication is not served from a stale index projection.
        row=service.store.get(candidate['pk'])
        if not row or row.get('status')!='PUBLISHED' or row.get('template_id')!=tid:continue
        reason=None
        if row['region']!=region or row['configuration_key']!=configuration_key(tid,cfg):reason='CONFIGURATION_OR_REGION'
        elif row['capability_revision']!=capability_revision(tid,cfg):reason='CAPABILITY_CHANGED'
        elif int(service.clock())-int(row['measured_at'])>p['max_benchmark_age_days']*86400:reason='EXPIRED'
        elif row['workload_fingerprint']!=fingerprint(normalize(tid,workload)):reason='WORKLOAD_CHANGED'
        elif row['application']['kind']=='OWNED_APPLICATION' and row.get('test_owner')!=owner:reason='APPLICATION_OWNER'
        elif application_revision is not None and row['application']['revision']!=application_revision:reason='APPLICATION_UNKNOWN_OR_CHANGED'
        elif application_revision is None and row['application']['kind']!='SAMPLE':reason='APPLICATION_UNKNOWN_OR_CHANGED'
        elif row['scenario']['revision']!=(scenario_revision or __import__('cloudhub.benchmark_agent',fromlist=['revision']).revision()):reason='SCENARIO_UNKNOWN_OR_CHANGED'
        elif row['generator_limited']:reason='GENERATOR_LIMITED'
        if reason:excluded.append({'benchmark_id':row['benchmark_id'],'reason':reason});continue
        same=row['application']['kind']=='OWNED_APPLICATION' and row.get('test_owner')==owner
        found.append({'benchmark_id':row['benchmark_id'],'evidence_level':'APPLICATION_VERIFIED' if same else 'SAMPLE_APPLICATION',
            'measured_at':row['measured_at'],'metrics':row['metrics'],'target_rate':row['target_rate'],'rate_unit':row['rate_unit'],
            'duration_s':row['duration_s'],'warmup_s':row['warmup_s'],'bottlenecks':row['bottlenecks'],'generator_location':row['generator_location'],
            'cache_state':row['cache_state'],'measurement_scope':row.get('measurement_scope'),'evidence_sha256':row['evidence_sha256'],'limits':row['limits'],'application':row['application'],'scenario':row['scenario']})
    return sorted(found,key=lambda r:r['measured_at'],reverse=True),excluded
