"""Publish only the reviewed six-field public config; conditional write + one invalidation."""
import argparse,hashlib,json
from pathlib import Path
from hosting import config,public_config
from build_pages_live import public_config as validate_public

def content(hosting,inventory):
    value=validate_public(public_config(config(hosting),inventory),hosting)
    return ('window.CLOUDHUB = Object.freeze('+json.dumps(value,ensure_ascii=False)+');\n').encode()

def restore_content(body,hosting,inventory):
    """Only a public-config snapshot for this same API/identity, never executable input."""
    c=config(hosting);text=body.decode('utf-8').strip();prefix='window.CLOUDHUB = Object.freeze('
    if not text.startswith(prefix) or not text.endswith(');'):raise ValueError('Expected an exact public config snapshot')
    value=json.loads(text[len(prefix):-2])
    validate_public(value,c if value.get('apiBase')==c['api_url'] else None)
    identity=inventory['cognito']
    if (value['clientId']!=identity['client_id'] or value['region']!=identity['region']
            or value['cognitoDomain']!=identity['hosted_domain']
            or value['apiBase'] not in (inventory['api']['endpoint'],c['api_url'])
            or value['redirectUri'] not in (c['frontend_url'],'https://'+inventory['frontend']['distribution_domain']+'/')):
        raise ValueError('Snapshot changes the reviewed API or identity')
    return body

def publish(session,hosting,inventory,expected_sha256,restore_body=None):
    c=config(hosting);front=inventory['frontend'];body=content(c,inventory) if restore_body is None else restore_content(restore_body,c,inventory)
    sha=lambda b:hashlib.sha256(b).hexdigest()
    if session.client('sts').get_caller_identity()['Account']!=c['ACCOUNT_ID']:raise ValueError('Wrong account')
    s3=session.client('s3',region_name=c['PRIMARY_REGION']);kw={'Bucket':front['bucket'],'ExpectedBucketOwner':c['ACCOUNT_ID']}
    if not all(s3.get_public_access_block(**kw)['PublicAccessBlockConfiguration'].values()):raise ValueError('Frontend bucket must remain private')
    cf=session.client('cloudfront');d=cf.get_distribution(Id=front['distribution_id'])['Distribution']
    if d['DomainName']!=front['distribution_domain'] or not any(o['DomainName'].startswith(front['bucket']+'.s3.') and o.get('OriginAccessControlId') for o in d['DistributionConfig']['Origins']['Items']):
        raise ValueError('Distribution does not serve the reviewed private frontend bucket')
    obj=s3.get_object(**kw,Key='config.js');current=obj['Body'].read()
    if sha(current) not in (expected_sha256,sha(body)):raise ValueError('config.js changed since review')
    changed=current!=body
    if changed:s3.put_object(**kw,Key='config.js',Body=body,IfMatch=obj['ETag'],ContentType='application/javascript; charset=utf-8',
        CacheControl='no-store,max-age=0',ServerSideEncryption='AES256',Metadata=obj.get('Metadata',{}))
    read=s3.get_object(**kw,Key='config.js')['Body'].read()
    if read!=body:raise ValueError('Config readback differs')
    # Content-addressed caller reference makes retries, including after a lost
    # PutObject/invalidation response, return the same invalidation.
    invalidation=cf.create_invalidation(DistributionId=front['distribution_id'],InvalidationBatch={
        'CallerReference':'cloudhub-hosting-config-'+sha(body),'Paths':{'Quantity':1,'Items':['/config.js']}})['Invalidation']
    return {'changed':changed,'config_sha256':sha(body),'invalidation_id':invalidation['Id'],'invalidation_status':invalidation['Status'],'paths':['/config.js']}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--inventory',type=Path,required=True)
    p.add_argument('--expected-before-sha256',required=True);p.add_argument('--profile');p.add_argument('--apply',action='store_true')
    p.add_argument('--restore-config',type=Path,help='Reviewed config.js snapshot; only this API, identity and old/new frontend hosts are permitted')
    args=p.parse_args();c=json.loads(args.config.read_text());i=json.loads(args.inventory.read_text())
    body=args.restore_config.read_bytes() if args.restore_config else None
    target=content(c,i) if body is None else restore_content(body,c,i)
    if not args.apply:print(json.dumps({'mode':'LOCAL_REVIEW','config_sha256':hashlib.sha256(target).hexdigest()}));return
    if not c.get('DNS_CHANGE_APPROVED'):raise ValueError('Reviewed domain deployment approval required')
    import boto3
    print(json.dumps(publish(boto3.Session(profile_name=args.profile,region_name=c['PRIMARY_REGION']),c,i,args.expected_before_sha256,body)))
if __name__=='__main__':main()
