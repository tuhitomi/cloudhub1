"""Merge a reviewed frontend origin into existing shared upload CORS only.

Never creates/adopts a bucket, changes lifecycle/versioning, or issues an upload.
"""
import argparse,json
from copy import deepcopy
from pathlib import Path
from hosting import config

def merge_origins(rules,hosting):
    c=config(hosting);out=deepcopy(rules);matched=False
    origin=c['frontend_url'].rstrip('/')
    for rule in out:
        if '*' in rule['AllowedOrigins']:raise ValueError('Wildcard upload origins require separate review')
        if 'POST' in rule['AllowedMethods'] and any(o in rule['AllowedOrigins'] for o in [origin,*c['TRANSITION_ORIGINS']]):
            rule['AllowedOrigins']=list(dict.fromkeys([*rule['AllowedOrigins'],origin]))
            matched=True
    if not matched:raise ValueError('No existing reviewed direct-POST CORS rule')
    return out

def apply(session,hosting,plan):
    c=config(hosting)
    if session.client('sts').get_caller_identity()['Account']!=c['ACCOUNT_ID'] or plan['expected_owner']!=c['ACCOUNT_ID']:
        raise ValueError('Wrong account')
    if merge_origins(plan['before'],c)!=plan['rules']:raise ValueError('CORS target differs from the central hosting origin')
    s3=session.client('s3',region_name=c['PRIMARY_REGION']);kw={'Bucket':plan['bucket'],'ExpectedBucketOwner':c['ACCOUNT_ID']}
    current=s3.get_bucket_cors(**kw)['CORSRules']
    if current==plan['rules']:return {'status':'NO_CHANGES','bucket':plan['bucket']}
    if current!=plan['before']:raise ValueError('CORS changed since review; inspect and prepare again')
    # Deliberately only this API: no wildcard addition, policy, lifecycle,
    # versioning, grant or object write. Existing headers/methods stay unchanged.
    s3.put_bucket_cors(**kw,CORSConfiguration={'CORSRules':plan['rules']})
    after=s3.get_bucket_cors(**kw)['CORSRules']
    if after!=plan['rules']:raise ValueError('CORS readback differs')
    return {'status':'APPLIED_AND_READ_BACK','bucket':plan['bucket'],'rules':after}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True)
    p.add_argument('--plan',type=Path,required=True);p.add_argument('--profile');p.add_argument('--apply',action='store_true')
    args=p.parse_args();c=json.loads(args.config.read_text());plan=json.loads(args.plan.read_text())
    if not args.apply:
        print(json.dumps({'mode':'LOCAL_REVIEW','matches':merge_origins(plan['before'],c)==plan['rules']}));return
    if not c.get('DNS_CHANGE_APPROVED'):raise ValueError('Domain deployment approval required')
    import boto3
    print(json.dumps(apply(boto3.Session(profile_name=args.profile,region_name=c['PRIMARY_REGION']),c,plan)))
if __name__=='__main__':main()
