"""Operator-only bounded scenarios for T01–T09. No user URL or resource creation.

plan is read-only. run requires the reviewed plan hash and repeats ownership,
deadline, inventory and ledger checks. Credentials/tokens never enter evidence.
"""
import argparse,base64,concurrent.futures,hashlib,json,os,pathlib,platform,re,subprocess,sys,time,uuid,threading
from datetime import datetime,timezone,timedelta
ROOT=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from cloudhub import benchmark_agent as agent
from cloudhub.catalog import configuration_key,resolve_configuration
from cloudhub.benchmarks import capability_revision
from cloudhub.workloads import SAMPLES,normalize,resource_assessment

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()
def source(args):
    import boto3
    from boto3.dynamodb.types import TypeDeserializer
    session=boto3.Session(profile_name=args.profile,region_name=args.control_region)
    account=session.client('sts').get_caller_identity()['Account'];ddb=session.client('dynamodb');decode=TypeDeserializer()
    control=session.client('cloudformation').describe_stacks(StackName=args.control_stack)['Stacks'][0]
    outputs={v['OutputKey']:v['OutputValue'] for v in control.get('Outputs',[])};parameters={v['ParameterKey']:v['ParameterValue'] for v in control.get('Parameters',[])}
    if outputs.get('TableName')!=args.table or int(parameters.get('BudgetMilliusd','0'))!=args.cap_milliusd:raise ValueError('Control stack/table/current budget does not match the reviewed plan')
    def row(key):return {k:decode.deserialize(v) for k,v in ddb.get_item(TableName=args.table,Key={'pk':{'S':key}},ConsistentRead=True).get('Item',{}).items()}
    env=row('E#'+args.environment)
    if not env or env.get('validation_run') is not True or env.get('status')!='READY' or env.get('lock') or env.get('deadline') is None or int(env['deadline'])<time.time()+args.duration+args.warmup+120:raise ValueError('An unlocked, live, isolated validation environment with enough remaining time is required. Continuous/user environments are excluded.')
    if env['template_id'] not in SAMPLES or env.get('region') not in {'ap-southeast-1','ap-northeast-1','us-east-1'}:raise ValueError('Unverified target provenance')
    region=env['region'];cf=session.client('cloudformation',region_name=region)
    stack=cf.describe_stacks(StackName=env['stack_id'])['Stacks'][0];tags={t['Key']:t['Value'] for t in stack.get('Tags',[])}
    if tags.get('cloudhub:environment')!=args.environment or tags.get('cloudhub:owner')!=env['owner_id'] or ':{}'.format(account)+':stack/' not in env['stack_id']:raise ValueError('Stack tags/account do not match')
    cfg=resolve_configuration(env['template_id'],env.get('configuration'));ledger=row('Q#GLOBAL')
    committed=int(ledger.get('reserved_milliusd',0))+int(ledger.get('observed_unreserved_milliusd',0))
    if args.cap_milliusd is None or committed+args.existing_allowances+args.cost_ceiling>args.cap_milliusd:raise ValueError('Reviewed forecast headroom is insufficient; no reservation is reset or refunded')
    inventory=cf.list_stack_resources(StackName=env['stack_id'])['StackResourceSummaries']
    ids=[{'id':r['PhysicalResourceId'],'type':r['ResourceType']} for r in inventory if r.get('PhysicalResourceId')]
    for resource in list(ids):
        if resource['type']=='AWS::AutoScaling::AutoScalingGroup':
            group=session.client('autoscaling',region_name=region).describe_auto_scaling_groups(AutoScalingGroupNames=[resource['id']])['AutoScalingGroups'][0]
            tags={v['Key']:v['Value'] for v in group['Tags']}
            if tags.get('cloudhub:environment')!=args.environment or tags.get('cloudhub:owner')!=env['owner_id']:raise ValueError('ASG ownership mismatch')
            ids.extend({'id':v['InstanceId'],'type':'AWS::EC2::Instance'} for v in group['Instances'])
    return session,env,cfg,ids,{'account':account,'region':region,'committed_forecast_milliusd':committed,'active':int(ledger.get('active',0)),'cap_milliusd':args.cap_milliusd}

def prepare(args):
    session,env,cfg,resources,budget=source(args);tid=env['template_id'];mode='IO' if tid in {'T01','T08'} else 'S3' if tid=='T07' else 'HTTP'
    if not args.workload:raise ValueError('An explicit measured workload JSON is required; UI example inputs are not benchmark observations')
    workload=normalize(tid,json.loads(args.workload.read_text(encoding='utf-8')))
    if resource_assessment(tid,cfg,workload)['status']=='NOT_FIT':raise ValueError('Workload is outside the deployed template capability; worker queues are not supported by T06')
    if mode=='IO' and args.duration*args.rate>100:raise ValueError('SSM stdout scenario is limited to 100 observations per node; use a reviewed larger raw-artifact transport for longer runs')
    if tid=='T04' and (args.duration<15 or args.engine!='python' or not args.peak_rate or args.peak_rate<args.rate or args.peak_rate*args.duration>10000):raise ValueError('T04 requires the bounded Python steady/step/peak scenario, a peak rate and at least 15 seconds; scale-out must actually be observed before publication')
    if mode=='HTTP' and (not args.expected_sha256 or not re.fullmatch('[a-f0-9]{64}',args.expected_sha256)):raise ValueError('Expected response checksum is required; do not bless an unknown response as correct')
    target=env.get('access_address') if mode=='HTTP' else None
    if mode=='HTTP':
        from urllib.parse import urlsplit
        parsed=urlsplit(target or '')
        if not parsed.hostname or parsed.query or parsed.fragment or parsed.username or parsed.password:raise ValueError('Stored application target is not safe')
        # Disallow the management hostnames independently of registry metadata.
        if parsed.hostname in {'cloudhub1.me','api.cloudhub1.me','d3qujq9kfq5gca.cloudfront.net','p3i0opiv22.execute-api.ap-southeast-1.amazonaws.com'}:raise ValueError('Management API measurements are not application evidence')
    if tid=='T02':
        distributions=[r['id'] for r in resources if r['type']=='AWS::CloudFront::Distribution']
        if len(distributions)!=1:raise ValueError('Missing test distribution')
        conf=session.client('cloudfront').get_distribution_config(Id=distributions[0])['DistributionConfig']
        behaviors=[conf['DefaultCacheBehavior'],*conf.get('CacheBehaviors',{}).get('Items',[])]
        if any(b.get('LambdaFunctionAssociations',{}).get('Quantity',0) for b in behaviors) or any(o.get('OriginShield',{}).get('Enabled') for o in conf['Origins']['Items']):raise ValueError('AWS forbids this CloudFront load-test configuration')
        import urllib.request
        # Follow the managed root's version redirect once during review, never
        # load-test the redirect itself or silently switch publications mid-run.
        request=urllib.request.Request(target,method='HEAD')
        with urllib.request.build_opener(agent.SameOriginRedirect()).open(request,timeout=5) as response:target=response.url
    plan={'schema':1,'environment_id':env['environment_id'],'template_id':tid,'region':env['region'],'configuration':cfg,
        'configuration_key':configuration_key(tid,cfg),'capability_revision':capability_revision(tid,cfg),'scenario_revision':agent.revision(),
        'isolation_owner':env['owner_id'],'isolated_validation':True,'stack_id':env['stack_id'],'inventory':resources,'budget':budget,'mode':mode,
        'target':target,'expected_sha256':args.expected_sha256,'duration_s':args.duration,'warmup_s':args.warmup,'rate':args.rate,'concurrency':args.concurrency,
        'engine':args.engine,'peak_rate':args.peak_rate,'t01_task':args.t01_task,'workload':workload,'cost_ceiling_milliusd':args.cost_ceiling,'existing_allowances_milliusd':args.existing_allowances,
        'generator_location':args.generator_location,'quota_snapshot':quota_snapshot(session,resources,env['region'],cfg,budget),'stop':'10% error budget after 10 attempts, deadline or generator bounds',
        'cleanup':'Only exact nonce test files/object versions are removed; environment retirement uses the existing mandatory-backup flow separately.',
        'scope':'One generator/location; no global CloudFront limit, no sustained burstable claim. T06 worker is not supported by the current service.'}
    return session,env,cfg,plan

def quota_snapshot(session,resources,region,cfg,budget):
    """Actual target settings, separate from forecast and unknown account quotas."""
    provider={};nodes=[r['id'] for r in resources if r['type']=='AWS::EC2::Instance']
    if nodes:
        ec2=session.client('ec2',region_name=region)
        provider['ec2_credit_modes']=ec2.describe_instance_credit_specifications(InstanceIds=nodes)['InstanceCreditSpecifications']
        provider['ec2_instances']=[{k:v[k] for k in ['InstanceId','InstanceType','ImageId','CpuOptions','SubnetId','VpcId'] if k in v} for group in ec2.describe_instances(InstanceIds=nodes)['Reservations'] for v in group['Instances']]
    for r in resources:
        kind=r['type'];rid=r['id']
        if kind=='AWS::Lambda::Function':
            client=session.client('lambda',region_name=region);provider['lambda_account']=client.get_account_settings()['AccountLimit'];provider['lambda_reserved']=client.get_function_concurrency(FunctionName=rid).get('ReservedConcurrentExecutions')
        elif kind=='AWS::DynamoDB::Table':
            table=session.client('dynamodb',region_name=region).describe_table(TableName=rid)['Table'];provider['dynamodb']={k:table[k] for k in ['BillingModeSummary','ProvisionedThroughput','OnDemandThroughput','WarmThroughput'] if k in table}
        elif kind=='AWS::AutoScaling::AutoScalingGroup':
            group=session.client('autoscaling',region_name=region).describe_auto_scaling_groups(AutoScalingGroupNames=[rid])['AutoScalingGroups'][0];provider['autoscaling']={k:group[k] for k in ['MinSize','MaxSize','DesiredCapacity','DefaultCooldown']}
        elif kind=='AWS::RDS::DBInstance':
            db=session.client('rds',region_name=region).describe_db_instances(DBInstanceIdentifier=rid)['DBInstances'][0];provider['rds']={k:db[k] for k in ['DBInstanceClass','Engine','EngineVersion','AllocatedStorage','StorageType','Iops','StorageThroughput','MaxAllocatedStorage','MultiAZ'] if k in db}
        elif kind=='AWS::EFS::FileSystem':
            fs=session.client('efs',region_name=region).describe_file_systems(FileSystemId=rid)['FileSystems'][0];provider['efs']={k:fs[k] for k in ['PerformanceMode','ThroughputMode','ProvisionedThroughputInMibps','SizeInBytes'] if k in fs}
        elif kind=='AWS::ApiGatewayV2::Api':
            provider['http_stages']=[{k:v[k] for k in ['StageName','RouteSettings','DefaultRouteSettings'] if k in v} for v in session.client('apigatewayv2',region_name=region).get_stages(ApiId=rid)['Items']]
        elif kind=='AWS::ECS::Service':
            cluster=next((v['id'] for v in resources if v['type']=='AWS::ECS::Cluster'),None)
            if not cluster:raise ValueError('Missing owned ECS cluster inventory')
            ecs=session.client('ecs',region_name=region);svc=ecs.describe_services(cluster=cluster,services=[rid])['services'][0];task=ecs.describe_task_definition(taskDefinition=svc['taskDefinition'])['taskDefinition']
            provider['ecs']={'desired_count':svc['desiredCount'],'running_count':svc['runningCount'],'task_cpu':task['cpu'],'task_memory':task['memory'],'images':[v['image'] for v in task['containerDefinitions']]}
    return {'observed_at':int(time.time()),'region':region,'configured_limits':cfg,'provider':provider,'budget_forecast_not_provider_quota':budget,
        'other_account_capacity_quotas':None,'scope':'Provider values were read for these exact isolated resources. Other EC2/RDS/Fargate account quotas are unqueried, never inferred as available capacity.'}

def metrics(session,resources,region):
    cw=session.client('cloudwatch',region_name=region);end=datetime.now(timezone.utc);start=end-timedelta(minutes=15);result={}
    specs={
      'AWS::EC2::Instance':('AWS/EC2','InstanceId',['CPUUtilization','CPUCreditBalance','CPUCreditUsage']),
      'AWS::RDS::DBInstance':('AWS/RDS','DBInstanceIdentifier',['CPUUtilization','DatabaseConnections','ReadLatency','WriteLatency','ReadIOPS','WriteIOPS']),
      'AWS::Lambda::Function':('AWS/Lambda','FunctionName',['Duration','Errors','Throttles','ConcurrentExecutions']),
      'AWS::DynamoDB::Table':('AWS/DynamoDB','TableName',['ConsumedReadCapacityUnits','ConsumedWriteCapacityUnits','ReadThrottleEvents','WriteThrottleEvents']),
      'AWS::EFS::FileSystem':('AWS/EFS','FileSystemId',['PercentIOLimit','BurstCreditBalance','MeteredIOBytes','PermittedThroughput'])}
    for resource in resources:
        if resource['type'] not in specs:continue
        ns,dimension,names=specs[resource['type']]
        for name in names:
            data=cw.get_metric_statistics(Namespace=ns,MetricName=name,Dimensions=[{'Name':dimension,'Value':resource['id']}],StartTime=start,EndTime=end,Period=300,Statistics=['Average','Maximum','Sum'])
            result[resource['id']+'/'+name]=sorted(data.get('Datapoints',[]),key=lambda v:v['Timestamp'])
    return result

def ssm_io(session,resources,region,tid,nonce,args):
    client=session.client('ssm',region_name=region);nodes=[r['id'] for r in resources if r['type']=='AWS::EC2::Instance']
    if len(nodes)!=(2 if tid=='T08' else 1):raise ValueError('Unexpected node inventory')
    def marker(node,index,action):
        command=client.send_command(InstanceIds=[node],DocumentName='AWS-RunShellScript',Parameters={'commands':[agent.remote_marker_script(nonce,index,action)]},TimeoutSeconds=60)['Command']['CommandId'];end=time.monotonic()+90
        while time.monotonic()<end:
            try:r=client.get_command_invocation(CommandId=command,InstanceId=node)
            except client.exceptions.InvocationDoesNotExist:time.sleep(1);continue
            if r['Status'] in {'Pending','InProgress','Delayed'}:time.sleep(1);continue
            if r['Status']!='Success':raise ValueError('Cross-client marker failed; preserve source and inspect the exact command')
            return json.loads(r['StandardOutputContent'])
        raise ValueError('Marker timeout; reconcile before cleaning exact probe markers')
    cross=[]
    if tid=='T08':
        for i,node in enumerate(nodes):marker(node,i,'create')
        for i,node in enumerate(nodes):cross.append(marker(node,1-i,'read'))
        for i,node in enumerate(nodes):marker(node,i,'cleanup')
    commands={}
    for index,node in enumerate(nodes):
        commands[node]=client.send_command(InstanceIds=[node],DocumentName='AWS-RunShellScript',Parameters={'commands':[agent.remote_io_script('/shared' if tid=='T08' else '/data',nonce[:-1]+str(index),args.duration,args.rate,args.concurrency,args.t01_task if tid=='T01' else 'io')]},TimeoutSeconds=args.duration+120)['Command']['CommandId']
    values=[];end=time.monotonic()+args.duration+120
    while commands and time.monotonic()<end:
        for node,command in list(commands.items()):
            try:result=client.get_command_invocation(CommandId=command,InstanceId=node)
            except client.exceptions.InvocationDoesNotExist:continue
            if result['Status'] in {'Pending','InProgress','Delayed'}:continue
            if result['Status']!='Success':raise ValueError('Probe command failed; inspect the isolated test command without publishing credentials')
            values.append(json.loads(result['StandardOutputContent']));del commands[node]
        if commands:time.sleep(2)
    if commands:raise ValueError('Probe command timed out; preserve source and reconcile the exact test command')
    return {'samples':[s for v in values for s in v['samples']],
        'execution':{**values[0]['execution'],'started_at':min(v['execution']['started_at'] for v in values),'ended_at':max(v['execution']['ended_at'] for v in values),
          'duration_s':max(v['execution']['ended_at'] for v in values)-min(v['execution']['started_at'] for v in values),'target_rate':args.rate*len(nodes)},'node_scopes':[v['scope'] for v in values],
        'cross_node_correctness':len(cross)==2 and all(v['correct'] for v in cross),'cross_node_checks':cross}

def run(args):
    before=json.loads(args.review.read_text(encoding='utf-8'));session,env,cfg,plan=prepare(args)
    if args.review_hash!=digest(before) or any(plan[k]!=before.get(k) for k in ['environment_id','stack_id','configuration_key','capability_revision','scenario_revision','duration_s','warmup_s','rate','concurrency','engine','peak_rate','t01_task','cost_ceiling_milliusd','workload','generator_location','expected_sha256','target']):raise ValueError('Reviewed plan/hash changed; review again')
    resources=plan['inventory'];region=env['region'];tid=env['template_id'];nonce=uuid.uuid4().hex[:24];cw_before=metrics(session,resources,region);pops=set();cache_observations=[];cleanup=lambda:None;scope={};wall=time.perf_counter()
    try:
        if plan['mode']=='IO':result=ssm_io(session,resources,region,tid,nonce,args)
        elif plan['mode']=='S3':
            buckets=[r['id'] for r in resources if r['type']=='AWS::S3::Bucket']
            if len(buckets)!=1:raise ValueError('Unexpected S3 inventory')
            s3=session.client('s3',region_name=region);tags={t['Key']:t['Value'] for t in s3.get_bucket_tagging(Bucket=buckets[0],ExpectedBucketOwner=plan['budget']['account'])['TagSet']}
            if tags.get('cloudhub:environment')!=env['environment_id'] or tags.get('cloudhub:owner')!=env['owner_id']:raise ValueError('Object scope mismatch')
            probe,cleanup,scope=agent.s3_probe(s3,buckets[0],plan['budget']['account'],nonce,cfg['max_file_bytes']);result=agent.bounded_arrival(probe,args.duration,args.rate,args.concurrency,args.warmup)
        elif args.engine=='k6':
            args.out.mkdir(parents=True,exist_ok=True);manifest=args.out/'k6-target.json';manifest.write_text(json.dumps(plan,default=str),encoding='utf-8')
            envvars={**os.environ,'CLOUDHUB_BENCH_MANIFEST':str(manifest.resolve())};log=args.out/'k6-output.private.log'
            with log.open('w',encoding='utf-8') as output:proc=subprocess.run(['k6','run',str(ROOT/'benchmarks/http.js')],cwd=args.out,env=envvars,stdout=output,stderr=subprocess.STDOUT,timeout=args.duration+args.warmup+90)
            samples=[];started=None;ended=None
            for line in log.read_text(encoding='utf-8').splitlines():
                if 'cloudhub_' not in line:continue
                # k6's console formatter quotes the JSON message. Decode it,
                # rather than extracting credentials or arbitrary HTTP logs.
                m=re.search(r'msg=("(?:[^"\\]|\\.)*")',line)
                if m:
                    message=json.loads(json.loads(m.group(1)))
                    if 'cloudhub_observation' in message:samples.append(message['cloudhub_observation'])
                    elif 'cloudhub_measurement_start' in message:started=message['cloudhub_measurement_start']
                    elif 'cloudhub_measurement_end' in message:ended=message['cloudhub_measurement_end']
                    elif 'cloudhub_cache' in message:cache_observations.append(message['cloudhub_cache'])
            if started is None or ended is None or ended<=started:raise ValueError('Actual k6 measurement timestamps missing; do not reconstruct them')
            summary=json.loads((args.out/'summary.json').read_text(encoding='utf-8'))
            result={'samples':samples,'execution':{'started_at':started,'ended_at':ended,'duration_s':ended-started,'warmup_s':args.warmup,'target_rate':args.rate,
                'dropped_iterations':int(summary.get('metrics',{}).get('dropped_iterations',{}).get('values',{}).get('count',0)),'stop_reason':'COMPLETED' if proc.returncode==0 else 'GENERATOR_LIMIT'}}
        else:
            probe=agent.http_probe(plan['target'],args.expected_sha256,token=os.getenv('CLOUDHUB_BENCH_TOKEN') if tid=='T09' else None,pops=pops,cache_observations=cache_observations if tid=='T02' else None)
            if tid=='T04':
                asg=next(r['id'] for r in resources if r['type']=='AWS::AutoScaling::AutoScalingGroup');scaler=session.client('autoscaling',region_name=region);timeline=[];phase='STEADY';stop=threading.Event();baseline=None
                def observe():
                    nonlocal baseline
                    while not stop.is_set():
                        group=scaler.describe_auto_scaling_groups(AutoScalingGroupNames=[asg])['AutoScalingGroups'][0];count=len(group['Instances']);baseline=count if baseline is None else baseline
                        timeline.append({'at':int(time.time()),'phase':'SCALE_OUT' if count>baseline else phase,'instances':count,'desired':group['DesiredCapacity']})
                        stop.wait(5)
                thread=threading.Thread(target=observe,daemon=True);thread.start();parts=[]
                try:
                    for phase,seconds,rate in [('STEADY',args.duration//3,args.rate),('RAMP',args.duration//3,args.peak_rate),('PEAK',args.duration-2*(args.duration//3),args.peak_rate)]:parts.append(agent.bounded_arrival(probe,seconds,rate,args.concurrency,args.warmup if not parts else 0))
                finally:stop.set();thread.join(timeout=10)
                execution={**parts[0]['execution'],'ended_at':parts[-1]['execution']['ended_at']};execution['duration_s']=execution['ended_at']-execution['started_at'];execution['target_rate']=str((args.duration//3*args.rate+(args.duration-args.duration//3)*args.peak_rate)/args.duration);execution['dropped_iterations']=sum(v['execution']['dropped_iterations'] for v in parts)
                execution['stop_reason']='COMPLETED' if all(v['execution']['stop_reason']=='COMPLETED' for v in parts) else 'GENERATOR_LIMIT'
                result={'samples':[s for v in parts for s in v['samples']],'execution':execution,'scaling_timeline':timeline}
            else:result=agent.bounded_arrival(probe,args.duration,args.rate,args.concurrency,args.warmup,on_measurement_start=cache_observations.clear)
    finally:cleanup()
    cw_after=metrics(session,resources,region)
    credits=lambda data:{k:v for k,v in data.items() if 'CPUCredit' in k}
    workload=plan['workload']
    cache_state=agent.classify_cache(cache_observations)
    report={'schema':1,'template_id':tid,'region':region,'configuration':cfg,'capability_revision':plan['capability_revision'],
        'application':{'kind':'SAMPLE','revision':args.application_revision,'dataset_revision':args.dataset_revision},
        'scenario':{'id':'cloudhub-'+tid.lower()+'-reference','revision':agent.revision(),'workload_schema':'workload-1'},'workload':workload,
        'infrastructure':{'configuration':cfg,'limits':{'managed_limits':cfg,'inventory':resources,'deadline':env['deadline']},'quota_snapshot':plan['quota_snapshot'],'application_artifact':args.application_revision},
        'generator':{'location':args.generator_location,'tool':args.engine if plan['mode']=='HTTP' else 'python-ssm-io' if plan['mode']=='IO' else 'python-s3-sdk','version':platform.python_version(),'cpu':os.cpu_count(),'memory_mib':args.generator_memory_mib,'model':'arrival-rate','max_concurrency':args.concurrency},
        'execution':{**result['execution'],'mode':'AWS_ISOLATED_TEST','environment_id':env['environment_id'],'rate_unit':'operations/s' if plan['mode']=='IO' else 'transfers/s' if plan['mode']=='S3' else 'requests/s'},
        'samples':result['samples'],'observations':{'cpu_credits_before':credits(cw_before),'cpu_credits_after':credits(cw_after),'cloudwatch':{'before':cw_before,'after':cw_after},
            'scaling_timeline':result.get('scaling_timeline',[]),'cache_state':cache_state if tid=='T02' else 'N/A','cache_observations':cache_observations,'data_correctness':bool(result['samples']) and all(s['correct'] for s in result['samples']),
            'cross_node_correctness':result.get('cross_node_correctness',False),'cross_node_checks':result.get('cross_node_checks',[]),
            'measurement_scope':'Single endpoint/body checksum for HTTP; file write/fsync/read transaction for I/O (not block IOPS); initial PUT plus measured GETs for S3. No management API capacity or global/sustained claims.',
            'cloudfront_pops':sorted(pops),'scope':scope,'node_scopes':result.get('node_scopes',[]),'wall_elapsed_s':time.perf_counter()-wall},
        'bottlenecks':['Inspect provider metrics and raw observations before publishing; a short test is not a sustained capacity claim.'],
        'evidence_files':[{'name':'raw-observations.json','sha256':digest(result['samples'])}]}
    args.out.mkdir(parents=True,exist_ok=True);raw=json.dumps(result['samples'],sort_keys=True,separators=(',',':')).encode();(args.out/'raw-observations.json').write_bytes(raw)
    (args.out/'report.json').write_text(json.dumps(report,indent=2,default=str),encoding='utf-8');print('Recorded raw evidence; NOT published. Review completeness, CPU credits, scaling and application identity first.')

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['plan','run']);p.add_argument('--profile',required=True);p.add_argument('--control-region',default='ap-southeast-1');p.add_argument('--table',required=True);p.add_argument('--environment',required=True);p.add_argument('--out',type=pathlib.Path,required=True)
    p.add_argument('--duration',type=int,default=15);p.add_argument('--warmup',type=int,default=2);p.add_argument('--rate',type=int,default=1);p.add_argument('--concurrency',type=int,default=2);p.add_argument('--engine',choices=['python','k6'],default='python');p.add_argument('--expected-sha256');p.add_argument('--generator-location',required=True);p.add_argument('--generator-memory-mib',type=int,required=True)
    p.add_argument('--control-stack',default='cloudhub-pages-live')
    p.add_argument('--peak-rate',type=int);p.add_argument('--t01-task',choices=['cpu','io'],default='io')
    p.add_argument('--cap-milliusd',type=int,required=True);p.add_argument('--existing-allowances',type=int,required=True);p.add_argument('--cost-ceiling',type=int,required=True);p.add_argument('--review',type=pathlib.Path);p.add_argument('--review-hash');p.add_argument('--application-revision');p.add_argument('--dataset-revision');p.add_argument('--workload',type=pathlib.Path)
    args=p.parse_args()
    if not re.fullmatch('env-[a-f0-9]{24}',args.environment) or not 1<=args.duration<=3600 or not 1<=args.rate<=100 or args.duration*args.rate>10000 or not 1<=args.concurrency<=16 or not 0<=args.warmup<=args.duration or args.cost_ceiling<=0 or args.existing_allowances<0:raise SystemExit('Invalid reviewed bounds')
    if args.action=='plan':
        _,_,_,value=prepare(args);args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(value,indent=2,default=str),encoding='utf-8');print('Review SHA-256: '+digest(value));return
    if not args.review or not args.review_hash or not all(re.fullmatch('[a-f0-9]{64}',v or '') for v in [args.application_revision,args.dataset_revision]):raise SystemExit('Run requires a reviewed plan hash plus known application/dataset hashes')
    run(args)

if __name__=='__main__':main()
