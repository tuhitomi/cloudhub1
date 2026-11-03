"""Read-only release inventory. Never invokes workflows, writes AWS data or resets a ledger."""
import argparse,json,os,sys,hashlib
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]

def inspect(session,account,region,stack,out):
    from botocore.config import Config
    from boto3.dynamodb.types import TypeDeserializer
    report={'recorded_at':datetime.now(timezone.utc).isoformat(),'mode':'AWS_READ_ONLY',
            'account':account,'region':region,'stack':stack,'aws_mutations':0,'observations':{},'errors':[]}
    def client(name,r=region):return session.client(name,region_name=r,config=Config(connect_timeout=5,read_timeout=15,retries={'max_attempts':1}))
    def read(name,fn):
        try:report['observations'][name]=fn();return report['observations'][name]
        except Exception as exc:
            report['errors'].append({'step':name,'type':type(exc).__name__,'code':getattr(exc,'response',{}).get('Error',{}).get('Code')});return None
    who=read('identity',lambda:client('sts').get_caller_identity()['Account'])
    if who!=account:
        report['status']='BLOCKED_SESSION_OR_ACCOUNT';return report
    cf=client('cloudformation');state=read('stack',lambda:cf.describe_stacks(StackName=stack)['Stacks'][0])
    if not state:report['status']='BLOCKED_STACK';return report
    # Template/rollback material stays outside the repository. Do not print it.
    template=cf.get_template(StackName=stack,TemplateStage='Original')['TemplateBody']
    template=json.loads(template) if isinstance(template,str) else template
    (out/'before-template.private.json').write_text(json.dumps(template,default=str,indent=2),encoding='utf-8')
    rows=cf.list_stack_resources(StackName=stack)['StackResourceSummaries'];physical={r['LogicalResourceId']:r.get('PhysicalResourceId') for r in rows}
    variables={};functions=[]
    allowed={'TABLE_NAME','BUDGET_MILLIUSD','USER_LIMIT','TOTAL_LIMIT','CONTINUOUS_ENABLED','DIRECT_UPLOAD_ENABLED',
             'PRICES_PARAMETER','REGIONAL_PRICES_PARAMETERS_JSON','REGIONS_PARAMETER','DRIVER_REGIONS_PARAMETER','DRIVER_SETTINGS_PARAMETER','USER_POOL_ID'}
    for name in ['ApiFunction','WorkerFunction','SweepFunction','ExpiryFunction']:
        value=client('lambda').get_function_configuration(FunctionName=physical[name])
        variables.update({k:v for k,v in value.get('Environment',{}).get('Variables',{}).items() if k in allowed})
        functions.append({'logical_id':name,'name':physical[name],'code_sha256':value['CodeSha256'],'last_modified':value['LastModified']})
    report['observations']['functions']=functions;report['observations']['runtime']=variables
    des=TypeDeserializer();ddb=client('dynamodb');table=variables['TABLE_NAME'];records=[];key=None
    # Bounded, projected metadata scan; never read file bytes/passwords/tokens.
    for _ in range(50):
        fields='pk kind owner_id environment_id operation_id status phase generation region retain_until deadline lifecycle_revision ledger_schema active reserved_milliusd future_reserved_milliusd accrued_estimate_milliusd legacy_unallocated_milliusd released_estimate_milliusd observed_unreserved_milliusd budget_milliusd version'.split()
        names={'#p'+str(i):name for i,name in enumerate(fields)}
        args={'TableName':table,'ConsistentRead':True,'Limit':100,
              'ProjectionExpression':','.join(names),'ExpressionAttributeNames':names}
        if key:args['ExclusiveStartKey']=key
        page=ddb.scan(**args);records.extend({k:des.deserialize(v) for k,v in item.items()} for item in page['Items'])
        key=page.get('LastEvaluatedKey')
        if not key:break
    # Migration must preserve *every* original quota field, not a projection.
    quotas=[]
    for r in records:
        if not r['pk'].startswith('Q#'):continue
        item=ddb.get_item(TableName=table,Key={'pk':{'S':r['pk']}},ConsistentRead=True).get('Item')
        if item:quotas.append({k:des.deserialize(v) for k,v in item.items()})
    (out/'quota-snapshot.private.json').write_text(json.dumps(quotas,default=lambda n:int(n),indent=2),encoding='utf-8')
    report['observations'].update(metadata_scan_truncated=bool(key),quota_snapshot=quotas,
        running_operations=[r for r in records if r.get('kind')=='operation' and r.get('status') in {'QUEUED','RUNNING'}],
        retained_recovery=[r for r in records if r.get('kind')=='recovery' and r.get('status') not in {'DELETED','EXPIRED'}],
        active_environments=[r for r in records if r.get('kind')=='environment' and r.get('status')!='DELETED'])
    parameters=set(v for k,v in variables.items() if k.endswith('_PARAMETER'))
    parameters.update(json.loads(variables.get('REGIONAL_PRICES_PARAMETERS_JSON','{}')).values())
    docs={}
    for name in sorted(parameters):
        value=read('parameter:'+name,lambda name=name:client('ssm').get_parameter(Name=name,WithDecryption=False)['Parameter'])
        if value:
            report['observations'].pop('parameter:'+name,None)
            # Config/price documents only, never decrypt or export SecureString.
            if value['Type']=='SecureString':continue
            docs[name]=json.loads(value['Value'])
            report['observations']['parameter:'+name]={'version':value['Version'],'sha256':hashlib.sha256(value['Value'].encode()).hexdigest()}
    (out/'runtime-documents.private.json').write_text(json.dumps(docs,default=str,indent=2),encoding='utf-8')
    read('free_tier_plan',lambda:client('freetier','us-east-1').get_account_plan_state())
    report['observations']['billing_actual']={'status':'NOT_READ','reason':'No paid Cost Explorer query is issued by this preflight; Free Tier plan/credits are separate from the internal ledger.'}
    for r in ['ap-southeast-1','ap-northeast-1','us-east-1']:
        read('stacks:'+r,lambda r=r:[{'name':s['StackName'],'status':s['StackStatus']} for s in client('cloudformation',r).describe_stacks()['Stacks'] if s['StackName'].startswith('cloudhub-')])
        read('volumes:'+r,lambda r=r:[{'id':v['VolumeId'],'state':v['State'],'gib':v['Size']} for v in client('ec2',r).describe_volumes(Filters=[{'Name':'tag-key','Values':['cloudhub:environment']}])['Volumes']])
        read('snapshots:'+r,lambda r=r:[{'id':s['SnapshotId'],'state':s['State'],'gib':s['VolumeSize']} for s in client('ec2',r).describe_snapshots(OwnerIds=[account],Filters=[{'Name':'tag-key','Values':['cloudhub:owner']}])['Snapshots']])
    # Strip stack parameters (which may be NoEcho) from the shareable inventory.
    report['observations']['stack']={'name':state['StackName'],'status':state['StackStatus'],'id':state['StackId']}
    report['status']='READ_COMPLETE_WITH_LIMITS' if report['errors'] or key else 'READ_COMPLETE'
    report['inventory_limits']=['Projected management records and EC2 storage are not a complete billing inventory; reconcile RDS/EFS/ECS/S3/AWS Backup before a paid test.','No paid resources may be started solely because this read succeeded.']
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--profile',required=True);p.add_argument('--account',required=True);p.add_argument('--region',default='ap-southeast-1');p.add_argument('--stack',default='cloudhub-pages-live');p.add_argument('--out-dir',type=Path,required=True)
    a=p.parse_args();out=a.out_dir.resolve()
    if out.is_relative_to(ROOT):p.error('Private native snapshots must stay outside the repository')
    out.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(ROOT.parents[1]/'work/deps'));import boto3
    report=inspect(boto3.Session(profile_name=a.profile,region_name=a.region),a.account,a.region,a.stack,out)
    (out/'preflight.json').write_text(json.dumps(report,default=str,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'account':a.account,'region':a.region,'aws_mutations':0,'errors':report['errors']}))
    return 0 if report['status'].startswith('READ_COMPLETE') else 2

if __name__=='__main__':raise SystemExit(main())
