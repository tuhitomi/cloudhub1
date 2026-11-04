"""F03 workload inputs describe demand, never inferred infrastructure capacity."""
from decimal import Decimal
from copy import deepcopy
from .catalog import ACTIVE_TEMPLATES
from .errors import HubError

VERSION='workload-1'
def number(key,unit,maximum=10**9,advanced=False):
    return {'key':key,'type':'integer','unit':unit,'minimum':0,'maximum':maximum,'advanced':advanced,'nullable':True,'label_key':'rec.field.'+key}
def choice(key,values,advanced=False):
    return {'key':key,'type':'enum','values':values,'advanced':advanced,'nullable':True,'label_key':'rec.field.'+key}
RESOURCE=[number('min_cpu_millicores','mCPU',64000,True),number('min_memory_mib','MiB',1048576,True)]
WEB=[number('active_users','users',1000000),number('actions_per_minute','actions/user/min',60000),
     number('api_calls_per_action','requests/action',1000,True),number('background_rps','requests/s',1000000,True),
     number('read_percent','%',100,True),choice('query_complexity',['SIMPLE','COMPLEX']),number('data_mib','MiB',10**8)]
FIELDS={
 'T01':[choice('job_kind',['SHELL','BUILD','BATCH','CUSTOM']),choice('software',['LIGHT_TOOLS','DATABASE','CUSTOM']),*RESOURCE,number('data_mib','MiB',10**8),choice('io_pattern',['SEQUENTIAL','RANDOM','MIXED']),number('jobs_per_minute','jobs/min',1000000),number('network_mib_per_hour','MiB/h',10**8,True)],
 'T02':[number('page_views_per_hour','pages/h',10**9),number('page_kib','KiB/page',10**8),number('assets_per_page','assets/page',10000),choice('viewer_geography',['US','EU','APAC','OTHER']),number('cache_hit_percent','%',100),number('data_kib','KiB',10**9),number('file_count','files',1000000,True),number('largest_file_kib','KiB',10**8,True)],
 'T03':[*WEB,*RESOURCE,number('response_kib','KiB/request',10**7,True),number('record_count','records',10**9,True),number('record_bytes','bytes/record',10**7,True)],
 'T04':[*WEB,number('peak_users','users',1000000),number('ramp_users_per_minute','users/min',1000000),*RESOURCE,number('response_kib','KiB/request',10**7,True),number('record_count','records',10**9,True),number('record_bytes','bytes/record',10**7,True)],
 'T05':[choice('website_kind',['STATIC','DYNAMIC','CUSTOM']),number('active_users','users',1000000),number('actions_per_minute','pages/user/min',60000),number('page_kib','KiB/page',10**8),number('data_mib','MiB',10**8),*RESOURCE],
 'T06':[choice('application_kind',['WEB','API','WORKER']),choice('image_source',['OPERATOR_APPROVED']),*RESOURCE,number('target_rps','requests/s',1000000),number('response_kib','KiB/request',10**7),number('data_kib','KiB',10**9),number('jobs_per_second','jobs/s',1000000,True),number('processing_ms','ms/job',900000,True),number('queue_depth','jobs',10**9,True)],
 'T07':[number('data_kib','KiB',10**9),number('largest_file_kib','KiB',10**8),number('file_count','files',1000000),number('uploads_per_hour','files/h',10**8),number('downloads_per_hour','files/h',10**8),number('transfer_concurrency','transfers',1000000),number('transfer_mib_per_hour','MiB/h',10**9)],
 'T08':[number('nodes','nodes',1000),number('data_mib','MiB',10**8),choice('file_kind',['SMALL','LARGE','MIXED']),choice('io_pattern',['SEQUENTIAL','RANDOM','MIXED']),number('throughput_mib_s','MiB/s',10**6,True),number('iops','operations/s',10**8,True),*RESOURCE,number('network_mib_per_hour','MiB/h',10**8,True)],
 'T09':[number('target_rps','requests/s',1000000),number('active_users','users',1000000,True),number('actions_per_minute','actions/user/min',60000,True),number('api_calls_per_action','requests/action',1000,True),number('background_rps','requests/s',1000000,True),number('processing_ms','ms/request',900000),number('request_kib','KiB/request',10240),number('response_kib','KiB/request',6144),number('reads_per_request','reads/request',100000,True),number('writes_per_request','writes/request',100000,True),number('record_count','records',10**9),number('record_bytes','bytes/record',10**7)]}

# These numbers are EXPLICIT illustrative demand inputs, not measured capacity.
SAMPLES={
 'T01':dict(job_kind='SHELL',software='LIGHT_TOOLS',min_cpu_millicores=500,min_memory_mib=512,data_mib=1024,io_pattern='MIXED',jobs_per_minute=1,network_mib_per_hour=10),
 'T02':dict(page_views_per_hour=100,page_kib=16,assets_per_page=4,viewer_geography='US',cache_hit_percent=90,data_kib=32,file_count=8,largest_file_kib=4),
 'T03':dict(active_users=5,actions_per_minute=2,api_calls_per_action=1,background_rps=0,read_percent=100,query_complexity='SIMPLE',data_mib=1,min_cpu_millicores=500,min_memory_mib=512,response_kib=4,record_count=16,record_bytes=128),
 'T04':dict(active_users=5,peak_users=10,ramp_users_per_minute=5,actions_per_minute=2,api_calls_per_action=1,background_rps=0,read_percent=100,query_complexity='SIMPLE',data_mib=1,min_cpu_millicores=500,min_memory_mib=512,response_kib=4,record_count=16,record_bytes=128),
 'T05':dict(website_kind='STATIC',active_users=5,actions_per_minute=2,page_kib=100,data_mib=1,min_cpu_millicores=500,min_memory_mib=512),
 'T06':dict(application_kind='WEB',image_source='OPERATOR_APPROVED',min_cpu_millicores=200,min_memory_mib=256,target_rps=1,response_kib=4,data_kib=0),
 'T07':dict(data_kib=32,largest_file_kib=4,file_count=8,uploads_per_hour=1,downloads_per_hour=10,transfer_concurrency=2,transfer_mib_per_hour=1),
 'T08':dict(nodes=2,data_mib=1,file_kind='SMALL',io_pattern='MIXED',throughput_mib_s=1,iops=1,min_cpu_millicores=500,min_memory_mib=512,network_mib_per_hour=1),
 'T09':dict(target_rps=1,processing_ms=100,request_kib=1,response_kib=1,reads_per_request=1,writes_per_request=0,record_count=16,record_bytes=128)}

# Explicit planning assumptions for optional technical fields. These describe
# the bundled workload/model, never CPU capacity or measured throughput.
BASIC_DEFAULTS={
 'T01':{'network_mib_per_hour':1},
 'T03':{'api_calls_per_action':1,'background_rps':0,'read_percent':100,'response_kib':4},
 'T04':{'api_calls_per_action':1,'background_rps':0,'read_percent':100,'response_kib':4},
 'T08':{'network_mib_per_hour':1},
 'T09':{'reads_per_request':1,'writes_per_request':0}}

def schema():
    result={'schema':VERSION,'sample_inputs_are_benchmarks':False,'templates':{
        tid:{'fields':deepcopy(FIELDS[tid]),'sample':deepcopy(SAMPLES[tid]),'sample_id':'example-1',
             'basic_defaults':deepcopy(BASIC_DEFAULTS.get(tid,{})),'defaults_are_capacity':False} for tid in sorted(ACTIVE_TEMPLATES)}}
    next(f for f in result['templates']['T06']['fields'] if f['key']=='application_kind')['supported_values']=['WEB','API']
    return result

def normalize(tid,value):
    if tid not in ACTIVE_TEMPLATES:raise HubError('TEMPLATE_UNAVAILABLE','Choose T01–T09.',409)
    if not isinstance(value,dict) or set(value)-{f['key'] for f in FIELDS[tid]}:
        raise HubError('WORKLOAD_INVALID','Use only workload fields for the selected template.',details={'field':'workload'})
    result={}
    for field in FIELDS[tid]:
        v=value.get(field['key']);key=field['key']
        if v is not None:
            if field['type']=='integer':
                if isinstance(v,Decimal) and v==v.to_integral_value():v=int(v)
                if type(v) is not int or not field['minimum']<=v<=field['maximum']:
                    raise HubError('WORKLOAD_INVALID','Choose an integer in the displayed range or Unknown.',details={'field':key})
            elif not isinstance(v,str) or v not in field['values']:
                raise HubError('WORKLOAD_INVALID','Choose a published value or Unknown.',details={'field':key})
        result[key]=v
    for key,value in BASIC_DEFAULTS.get(tid,{}).items():
        if result.get(key) is None:result[key]=value
    if tid in {'T02','T07'} and all(result.get(k) is not None for k in ['data_kib','file_count','largest_file_kib']) and result['data_kib']>result['file_count']*result['largest_file_kib']:
        raise HubError('WORKLOAD_CONFLICT','Stored data exceeds the declared file count and maximum file size.',details={'field':'data_kib'})
    return result

def demand(tid,w,hours):
    """Units explicitly distinguish work requested from throughput observed."""
    D=lambda key:Decimal(w[key]) if w.get(key) is not None else None
    def product(*keys):
        values=[D(k) for k in keys]
        return None if None in values else __import__('functools').reduce(lambda a,b:a*b,values,Decimal(1))
    rps=None;metrics={};duration=Decimal(str(hours))*3600
    if tid in {'T03','T04','T09'}:
        converted=product('active_users','actions_per_minute','api_calls_per_action')
        converted=None if converted is None or D('background_rps') is None else converted/60+D('background_rps')
        rps=D('target_rps') if tid=='T09' and D('target_rps') is not None else converted
        if tid=='T09' and D('target_rps') is not None and converted is not None and abs(rps-converted)>Decimal('.000001'):
            raise HubError('WORKLOAD_CONFLICT','Choose direct request rate or a matching user/action scenario.',details={'field':'target_rps'})
        metrics['target_rps']=rps
        if tid=='T04':
            peak=product('peak_users','actions_per_minute','api_calls_per_action')
            metrics['peak_rps']=None if peak is None or D('background_rps') is None else peak/60+D('background_rps')
        if tid=='T09':metrics['required_concurrency']=None if rps is None or D('processing_ms') is None else rps*D('processing_ms')/1000
    elif tid=='T02':
        pages=D('page_views_per_hour');assets=D('assets_per_page')
        metrics.update(page_views=None if pages is None else pages*Decimal(str(hours)),
            asset_requests=None if pages is None or assets is None else pages*(assets+1)*Decimal(str(hours)),
            transfer_gib=None if pages is None or D('page_kib') is None else pages*D('page_kib')*Decimal(str(hours))/1048576)
        metrics['origin_requests']=None if metrics['asset_requests'] is None or D('cache_hit_percent') is None else metrics['asset_requests']*(100-D('cache_hit_percent'))/100
    elif tid=='T05':
        value=product('active_users','actions_per_minute');rps=None if value is None else value/60;metrics['page_requests_per_second']=rps
    elif tid=='T06':
        metrics['target_jobs_per_second' if w.get('application_kind')=='WORKER' else 'target_rps']=D('jobs_per_second' if w.get('application_kind')=='WORKER' else 'target_rps')
        rps=D('target_rps') if w.get('application_kind')!='WORKER' else None
    elif tid=='T07':metrics.update(upload_requests=None if D('uploads_per_hour') is None else D('uploads_per_hour')*Decimal(str(hours)),download_requests=None if D('downloads_per_hour') is None else D('downloads_per_hour')*Decimal(str(hours)),target_concurrent_transfers=D('transfer_concurrency'),transfer_gib=None if D('transfer_mib_per_hour') is None else D('transfer_mib_per_hour')*Decimal(str(hours))/1024)
    elif tid=='T08':metrics.update(target_throughput_mib_s=D('throughput_mib_s'),target_iops=D('iops'),nodes=D('nodes'))
    else:metrics['target_jobs_per_minute']=D('jobs_per_minute')
    if rps is not None:metrics['requests']=rps*duration
    if tid in {'T03','T04','T06','T09'}:metrics['transfer_gib']=None if rps is None or D('response_kib') is None else rps*duration*D('response_kib')/1048576
    elif tid=='T05':metrics['transfer_gib']=None if rps is None or D('page_kib') is None else rps*duration*D('page_kib')/1048576
    elif tid in {'T01','T08'}:metrics['transfer_gib']=None if D('network_mib_per_hour') is None else D('network_mib_per_hour')*Decimal(str(hours))/1024
    return {k:None if v is None else str(v) for k,v in metrics.items()}

def resource_assessment(tid,cfg,w,headroom_percent=0,hours=1):
    """Hard catalog constraints only. CPU/RAM matching is not a load benchmark."""
    failures=[];unknown=[];adjust=[];optional=[]
    def check(field,available,component):
        v=w.get(field)
        if v is None:
            (optional if next((f['advanced'] for f in FIELDS[tid] if f['key']==field),False) else unknown).append(field)
            return
        needed=Decimal(v)*(100+headroom_percent)/100
        if needed>available:failures.append({'code':'RESOURCE_LIMIT','field':field,'required':str(needed),'available':available,'component':component})
    if tid in {'T01','T03','T04','T05','T06','T08'}:
        check('min_cpu_millicores',cfg['cpu']*1000//1024 if tid=='T06' else 2000,'container' if tid=='T06' else 'EC2')
        check('min_memory_mib',cfg['memory_mib'] if tid=='T06' else 1024,'container' if tid=='T06' else 'EC2')
        adjust.append('rec.adjust.cpu')
    if tid in {'T01','T05'}:check('data_mib',cfg['data_gib']*1024,'EBS /data');adjust.append('rec.adjust.disk')
    if tid in {'T03','T04'}:check('data_mib',cfg['db_gib']*1024,'RDS');adjust+=['rec.adjust.database','rec.limit.demoRecords']
    if tid in {'T02','T07','T06'}:
        check('data_kib',cfg['max_total_bytes']//1024,'managed S3')
        if tid in {'T02','T07'}:
            check('largest_file_kib',cfg['max_file_bytes']//1024,'managed S3 file');check('file_count',cfg['max_files'],'managed S3 files')
        adjust.append('rec.adjust.files')
    if tid in {'T03','T04','T09'}:
        if w.get('record_count') is not None:check('record_count',cfg['max_records'],'managed database API')
        if w.get('record_bytes') is not None:check('record_bytes',cfg['max_record_bytes'],'managed database record')
    if tid=='T04':adjust+=['rec.limit.scaling','rec.limit.databaseShared']
    if tid=='T06':
        adjust.append('rec.limit.approvedImage')
        if w.get('application_kind')=='WORKER':failures.append({'code':'WORKER_NOT_SUPPORTED','field':'application_kind','component':'current ECS service/ALB'})
    if tid=='T08':check('nodes',cfg['nodes'],'EFS access nodes');adjust+=['rec.limit.efsScope','rec.adjust.efs']
    if tid=='T07' and w.get('uploads_per_hour') is not None and w['uploads_per_hour']*hours>cfg['max_writes']:
        failures.append({'code':'WRITE_LIMIT','field':'uploads_per_hour','available':cfg['max_writes'],'component':'lifetime managed write limit'})
    if tid=='T09':
        if w.get('writes_per_request',0):failures.append({'code':'PUBLIC_API_READ_ONLY','field':'writes_per_request','available':0,'component':'current public API; mutations use CloudHub management'})
        target=demand(tid,w,hours).get('target_rps')
        if target is not None and Decimal(target)>5:failures.append({'code':'API_RATE_LIMIT','field':'target_rps','available':5,'component':'current HTTP API rate setting'})
        if w.get('processing_ms') is not None and w['processing_ms']>5000:failures.append({'code':'LAMBDA_TIMEOUT','field':'processing_ms','available':5000,'component':'current Lambda timeout'})
    if tid=='T09':adjust+=['rec.limit.sharedConcurrency','rec.adjust.serverless']
    if tid in {'T01','T03','T04','T05','T08'}:adjust.append('rec.limit.cpuCredits')
    unknown+= [f['key'] for f in FIELDS[tid] if not f['advanced'] and w.get(f['key']) is None]
    return {'status':'NOT_FIT' if failures else 'RESOURCE_FIT' if not unknown else 'NEEDS_INFORMATION','failures':failures,'unknown_fields':list(dict.fromkeys(unknown)),'optional_unchecked_fields':optional,'guidance_keys':list(dict.fromkeys(adjust)),
        'not_a_capacity_or_availability_guarantee':True,'headroom_percent':headroom_percent}
