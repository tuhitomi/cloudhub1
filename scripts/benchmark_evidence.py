"""Stage immutable private evidence, then use administrator JWT import/publication.

The raw files and report stay in the existing private artifact bucket. No public
URL, credentials or user resource is written by this tool.
"""
import argparse,hashlib,json,os,re,sys,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'backend'))
from cloudhub.benchmarks import MAX_BYTES,_safe_json

def stage(profile,region,bucket,report_path):
    import boto3
    blob=report_path.read_bytes();value=json.loads(blob);_safe_json(value)
    if len(blob)>MAX_BYTES or value.get('execution',{}).get('mode')!='AWS_ISOLATED_TEST' or set(value)-{'schema','template_id','region','configuration','capability_revision','application','scenario','workload','infrastructure','generator','execution','samples','observations','bottlenecks','evidence_files'}:raise ValueError('Only complete, non-fixture AWS evidence can be staged')
    session=boto3.Session(profile_name=profile,region_name=region);account=session.client('sts').get_caller_identity()['Account']
    # Use the existing reviewed deployment bucket scope; never choose a user
    # environment bucket or create a new bucket to make publication work.
    if bucket!='cloudhub-'+account+'-'+region+'-deploy':raise ValueError('Use the existing account/control-Region private artifact bucket')
    s3=session.client('s3');protection=s3.get_public_access_block(Bucket=bucket,ExpectedBucketOwner=account)['PublicAccessBlockConfiguration']
    if not all(protection.values()):raise ValueError('Evidence bucket must block all public access')
    digest=hashlib.sha256(blob).hexdigest();items=[];size=len(blob)
    if not 1<=len(value.get('evidence_files',[]))<=3:raise ValueError('Supply 1–3 raw evidence files')
    for reference in value['evidence_files']:
        name=reference['name']
        if not re.fullmatch('[A-Za-z0-9_.-]{1,100}',name):raise ValueError('Unsafe evidence filename')
        source=report_path.parent/name
        if source.is_symlink():raise ValueError('No symlinked source evidence')
        data=source.read_bytes();size+=len(data)
        if len(data)>MAX_BYTES or size>MAX_BYTES*2 or hashlib.sha256(data).hexdigest()!=reference['sha256']:raise ValueError('Raw evidence digest/size mismatch')
        if name.endswith('.json'):
            raw=json.loads(data);_safe_json(raw)
            if name=='raw-observations.json' and raw!=value.get('samples'):raise ValueError('Raw observations do not match the report')
        items.append(('evidence/'+name,data))
    if not any(v['name']=='raw-observations.json' for v in value['evidence_files']):raise ValueError('Include the immutable raw-observations.json source')
    items.append(('report.json',blob))
    for suffix,data in items:
        key='benchmarks/v1/'+digest+'/'+suffix
        try:s3.put_object(Bucket=bucket,Key=key,Body=data,IfNoneMatch='*',ExpectedBucketOwner=account,ContentType='application/json',ServerSideEncryption='AES256')
        except Exception as error:
            if getattr(error,'response',{}).get('Error',{}).get('Code') not in {'PreconditionFailed','412'}:raise
            existing=s3.get_object(Bucket=bucket,Key=key,ExpectedBucketOwner=account)['Body'].read(MAX_BYTES+1)
            if hashlib.sha256(existing).digest()!=hashlib.sha256(data).digest():raise ValueError('Immutable object conflict')
    return {'evidence_sha256':digest,'objects':len(items),'published':False,'next':'Administrator must import, review and explicitly publish through the API.'}

def command(api,method,path,body=None):
    token=os.getenv('CLOUDHUB_ACCESS_TOKEN')
    if not api.startswith('https://') or not token:raise ValueError('Use the configured HTTPS CloudHub API and a current admin token in CLOUDHUB_ACCESS_TOKEN; never place the token in arguments or source files')
    request=urllib.request.Request(api.rstrip('/')+path,method=method,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},data=None if body is None else json.dumps(body).encode())
    with urllib.request.urlopen(request,timeout=20) as response:return json.loads(response.read())

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['stage','import','publish','retire','list']);p.add_argument('--profile');p.add_argument('--region',default='ap-southeast-1');p.add_argument('--bucket');p.add_argument('--report',type=Path);p.add_argument('--api');p.add_argument('--evidence-sha256');p.add_argument('--benchmark-id');p.add_argument('--reviewed',action='store_true')
    args=p.parse_args()
    if args.action=='stage':
        if not all([args.profile,args.bucket,args.report]):p.error('stage requires --profile, --bucket and --report')
        print(json.dumps(stage(args.profile,args.region,args.bucket,args.report)));return
    if not args.api:p.error('--api is required')
    if args.action=='list':result=command(args.api,'GET','/admin/benchmarks')
    else:
        if not re.fullmatch('[a-f0-9]{64}',args.evidence_sha256 or ''):p.error('Use the staged evidence digest')
        if args.action=='import':result=command(args.api,'POST','/admin/benchmarks',{'evidence_sha256':args.evidence_sha256})
        else:
            if not args.reviewed or not re.fullmatch('bench-[a-f0-9]{24}',args.benchmark_id or ''):p.error('Publication/retirement requires --reviewed and the exact benchmark ID')
            result=command(args.api,'POST','/admin/benchmarks/'+args.benchmark_id+'/'+args.action,{'evidence_sha256':args.evidence_sha256,'reviewed':True})
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
