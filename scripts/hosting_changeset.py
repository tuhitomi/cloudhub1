"""Create a reviewable native CloudFormation changeset; execute is separate.

Every mutating command requires --approved after an administrator's review.
No domain registration, hosted-zone creation or automatic regional migration.
"""
import argparse,hashlib,json,subprocess
from pathlib import Path
from hosting import PROTECTED_TYPES

def certificate_guard(session,t,parameters,previous,account,region):
    from hosting import certificate_arn,covers
    def check(value,names,expected_region):
        arn=parameters.get(value['Ref'],previous.get(value['Ref'],{}).get('ParameterValue')) if isinstance(value,dict) and set(value)=={'Ref'} else value
        certificate_arn(arn or '',account,expected_region)
        d=session.client('acm',region_name=expected_region).describe_certificate(CertificateArn=arn)['Certificate']
        if d['Status']!='ISSUED' or any(not any(covers(s,n) for s in d.get('SubjectAlternativeNames',[d['DomainName']])) for n in names):
            raise ValueError('Certificate is not issued or does not cover the configured hostnames')
    for r in t['Resources'].values():
        p=r.get('Properties',{})
        if r['Type']=='AWS::CloudFront::Distribution':
            d=p['DistributionConfig'];cert=d.get('ViewerCertificate',{}).get('AcmCertificateArn')
            if cert:check(cert,d.get('Aliases',[]),'us-east-1')
        if r['Type']=='AWS::ApiGatewayV2::DomainName':
            for d in p['DomainNameConfigurations']:check(d['CertificateArn'],[p['DomainName']],region)

def dns_guard(session,t,review):
    """Check only this plan's records; never overwrite an unrelated namespace."""
    zones=set();names=[]
    for r in t['Resources'].values():
        p=r.get('Properties',{})
        if r['Type']=='AWS::Route53::RecordSet':
            if p['Type'] not in ('A','AAAA') or p['Name'].rstrip('.') not in review['allowed_dns_names']:
                raise ValueError('DNS record outside reviewed CloudHub scope')
            zones.add(p['HostedZoneId']);names.append(p['Name'].rstrip('.'))
        if r['Type']=='AWS::CertificateManager::Certificate':
            for d in p.get('DomainValidationOptions',[]):
                if d.get('HostedZoneId'):
                    zones.add(d['HostedZoneId']);names.append(d['DomainName'])
    for zone in zones:
        if not review.get('dns_change_approved'):raise ValueError('DNS validation or routing changes require approval in the reviewed configuration')
        if zone!=review['hosted_zone_id']:raise ValueError('Hosted zone differs from review')
        z=session.client('route53').get_hosted_zone(Id=zone)
        from hosting import host,under
        zone_name=host(z['HostedZone']['Name'])
        if z['HostedZone']['Config']['PrivateZone'] or any(not under(n,zone_name) for n in names):raise ValueError('Private or mismatched hosted zone')
        script="require('node:dns').promises.resolveNs(process.argv[1]).then(x=>console.log(JSON.stringify(x))).catch(()=>process.exit(1))"
        r=subprocess.run(['node','-e',script,zone_name],capture_output=True,text=True,check=True)
        observed={n.lower().rstrip('.') for n in json.loads(r.stdout)}
        if observed!={n.lower().rstrip('.') for n in z['DelegationSet']['NameServers']}:raise ValueError('Public DNS is not delegated to the selected zone')

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def checked_template(path,review):
    path=Path(path)
    if review['sha256'].get(path.name)!=digest(path):raise ValueError('Template differs from the reviewed file')
    return json.loads(path.read_text(encoding='utf-8'))

def completed(detail):
    return detail.get('Status')=='CREATE_COMPLETE' and detail.get('ExecutionStatus')=='EXECUTE_COMPLETE'

def validate_changes(detail,template,kind,baseline=None):
    if detail['Status']!='CREATE_COMPLETE' or detail.get('ExecutionStatus')!='AVAILABLE':raise ValueError('Changeset is not executable')
    for item in detail.get('Changes',[]):
        c=item['ResourceChange'];name=c['LogicalResourceId'];typ=c['ResourceType'];action=c['Action']
        if action=='Add' and typ=='AWS::CloudFront::Distribution':raise ValueError('Reuse the distribution with IMPORT; never create a duplicate')
        if c.get('Replacement') in ('True','Conditional') and typ in PROTECTED_TYPES:raise ValueError('Protected resource replacement: '+name)
        if action=='Remove':
            if kind=='IMPORT' or name not in {'FrontendDistribution','OriginAccess','UiCountryOriginPolicy'} or typ not in {'AWS::CloudFront::Distribution','AWS::CloudFront::OriginAccessControl','AWS::CloudFront::OriginRequestPolicy'}:
                raise ValueError('Unexpected resource removal: '+name)
            # Source detach is allowed only after the retain template was deployed.
        if kind=='IMPORT' and action!='Import':raise ValueError('IMPORT cannot create or modify resources')
        if action in ('Add','Modify') and typ.startswith('AWS::IAM::'):
            # CFN propagates a Retain-only edge change through existing Lambda
            # ARNs to an otherwise unchanged scheduler role. Accept only the
            # identical native resource and exclusively dynamic dependencies.
            details=c.get('Details',[])
            unchanged=(action=='Modify' and c.get('Replacement')=='False' and baseline is not None
                and baseline.get('Resources',{}).get(name)==template.get('Resources',{}).get(name)
                and bool(details) and all(d.get('Evaluation')=='Dynamic' and d.get('ChangeSource')=='ResourceAttribute' for d in details))
            if not unchanged:raise ValueError('Hosting changes must not expand IAM')
    return True

def template_location(cf_session,body,bucket,account):
    if len(body)<=51200:return {'TemplateBody':body.decode('utf-8')}
    if not bucket:raise ValueError('Large existing SAM template requires the approved existing --artifact-bucket')
    s3=cf_session.client('s3');s3.head_bucket(Bucket=bucket,ExpectedBucketOwner=account)
    if not all(s3.get_public_access_block(Bucket=bucket)['PublicAccessBlockConfiguration'].values()):raise ValueError('Artifact bucket must remain private')
    region=s3.get_bucket_location(Bucket=bucket).get('LocationConstraint') or 'us-east-1'
    if region=='EU':region='eu-west-1'
    key='hosting-review/'+hashlib.sha256(body).hexdigest()+'.json'
    s3.put_object(Bucket=bucket,Key=key,Body=body,ContentType='application/json',ServerSideEncryption='AES256',ExpectedBucketOwner=account)
    return {'TemplateURL':'https://'+bucket+'.s3.'+region+'.amazonaws.com/'+key}

def main(session=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['create','execute','wait-certificate','wait-edge'])
    p.add_argument('--review',type=Path,required=True);p.add_argument('--profile');p.add_argument('--region',required=True);p.add_argument('--approved',action='store_true')
    p.add_argument('--stack');p.add_argument('--template',type=Path);p.add_argument('--parameters',type=Path);p.add_argument('--kind',choices=['CREATE','UPDATE','IMPORT'],default='UPDATE')
    p.add_argument('--imports',type=Path);p.add_argument('--artifact-bucket');p.add_argument('--manifest',type=Path);p.add_argument('--resource-id')
    args=p.parse_args();review=json.loads(args.review.read_text(encoding='utf-8'))
    import boto3
    session=session or boto3.Session(profile_name=args.profile,region_name=args.region);cf=session.client('cloudformation',region_name=args.region)
    if session.client('sts').get_caller_identity()['Account']!=review['account_id']:p.error('Wrong AWS account')
    if args.region not in {review['primary_region'],review['shared_stack_region'],'us-east-1'}:p.error('Region is outside this hosting review')
    if args.action=='wait-certificate':
        from hosting import certificate_arn
        certificate_arn(args.resource_id or '',review['account_id'],args.region)
        session.client('acm',region_name=args.region).get_waiter('certificate_validated').wait(CertificateArn=args.resource_id,WaiterConfig={'Delay':15,'MaxAttempts':120});return
    if args.action=='wait-edge':
        session.client('cloudfront').get_waiter('distribution_deployed').wait(Id=args.resource_id,WaiterConfig={'Delay':15,'MaxAttempts':120});return
    if not args.approved:p.error('Review resource/cost/DNS/rollback scope first, then supply --approved explicitly')
    if review.get('mode')=='CUTOVER_PREPARED_NOT_EXECUTED' and review.get('blockers'):p.error('Cutover readiness checks are incomplete; --approved cannot bypass them')
    if not args.template or not args.manifest:p.error('--template and --manifest required')
    t=checked_template(args.template,review)
    dns_guard(session,t,review)
    review_hash=digest(args.review)
    if args.action=='create':
        if not args.stack or not args.stack.startswith('cloudhub-'):p.error('An explicit CloudHub stack name is required')
        parameters=checked_template(args.parameters,review) if args.parameters else {}
        if not isinstance(parameters,dict):p.error('Parameters must be a reviewed JSON object')
        if any(k not in t.get('Parameters',{}) for k in parameters):p.error('Unexpected parameter in reviewed inputs')
        if any(t['Parameters'][k].get('NoEcho') for k in parameters):raise ValueError('Secret parameters must not be written to review files')
        previous={}
        baseline=None
        if args.kind=='UPDATE':
            previous={v['ParameterKey']:v for v in cf.describe_stacks(StackName=args.stack)['Stacks'][0].get('Parameters',[])}
            baseline=cf.get_template(StackName=args.stack,TemplateStage='Original')['TemplateBody']
            if isinstance(baseline,str):baseline=json.loads(baseline)
        certificate_guard(session,t,parameters,previous,review['account_id'],args.region)
        if args.kind=='IMPORT' and 'UiEdgeSecret' in t.get('Parameters',{}) and 'UiEdgeSecret' not in parameters:
            # Reuse the exact origin-only secret privately; never put it into a
            # template default, file, manifest or printed request.
            d=session.client('cloudfront').get_distribution_config(Id=review['existing_distribution_id'])['DistributionConfig']
            keys=[h['HeaderValue'] for o in d['Origins']['Items'] for h in o.get('CustomHeaders',{}).get('Items',[]) if h['HeaderName'].lower()=='x-cloudhub-edge-key']
            if len(keys)!=1:raise ValueError('Cannot identify the existing private country-origin key')
            parameters['UiEdgeSecret']=keys[0]
        for name,schema in t.get('Parameters',{}).items():
            if schema.get('NoEcho') and name in parameters and not (args.kind=='IMPORT' and name=='UiEdgeSecret'):
                raise ValueError('Do not put secrets into parameter files; preserve the existing private parameter')
        values=[]
        for key,schema in t.get('Parameters',{}).items():
            if key in parameters:values.append({'ParameterKey':key,'ParameterValue':str(parameters[key])})
            elif key in previous:values.append({'ParameterKey':key,'UsePreviousValue':True})
            elif 'Default' not in schema:raise ValueError('Missing explicit parameter '+key+'; secrets must be supplied privately')
        parameter_hash=digest(args.parameters)[:10] if args.parameters else 'previous'
        req={'StackName':args.stack,'ChangeSetName':'hosting-'+review_hash[:16]+'-'+digest(args.template)[:12]+'-'+parameter_hash,
            'ChangeSetType':args.kind,'Description':'CloudHub hosting reviewed '+review_hash,'Parameters':values,
            **template_location(session,args.template.read_bytes(),args.artifact_bucket,review['account_id'])}
        caps=[]
        if any(r['Type'].startswith('AWS::IAM::') or r['Type']=='AWS::Serverless::Function' for r in t['Resources'].values()):caps.append('CAPABILITY_NAMED_IAM')
        if t.get('Transform'):caps.append('CAPABILITY_AUTO_EXPAND')
        if caps:req['Capabilities']=caps
        if args.kind=='IMPORT':
            if not args.imports or review['sha256'].get(args.imports.name)!=digest(args.imports):raise ValueError('Exact reviewed import identifiers required')
            req['ResourcesToImport']=json.loads(args.imports.read_text(encoding='utf-8'))
            if not req['ResourcesToImport'] or any(not v for r in req['ResourcesToImport'] for v in r['ResourceIdentifier'].values()):raise ValueError('Import physical IDs must be complete')
        try:result=cf.create_change_set(**req)
        except cf.exceptions.AlreadyExistsException:
            result=cf.describe_change_set(StackName=args.stack,ChangeSetName=req['ChangeSetName']);result={'Id':result['ChangeSetId'],'StackId':result['StackId']}
        try:cf.get_waiter('change_set_create_complete').wait(ChangeSetName=result['Id'],WaiterConfig={'Delay':5,'MaxAttempts':120})
        except Exception:
            d=cf.describe_change_set(ChangeSetName=result['Id'])
            if d['Status']=='FAILED' and any(s in d.get('StatusReason','').lower() for s in ("didn't contain changes",'no updates are to be performed')):
                args.manifest.write_text(json.dumps({'status':'NO_CHANGES','review_sha256':review_hash,'template_sha256':digest(args.template),'region':args.region}),encoding='utf-8');print('NO_CHANGES');return
            raise
        detail=cf.describe_change_set(ChangeSetName=result['Id'])
        if not completed(detail):validate_changes(detail,t,args.kind,baseline)
        manifest={'status':'ALREADY_EXECUTED' if completed(detail) else 'REVIEW_CHANGESET_BEFORE_EXECUTION','change_set_id':result['Id'],'stack_id':result['StackId'],'kind':args.kind,
            'region':args.region,'review_sha256':review_hash,'template_sha256':digest(args.template),
            'changes':[{k:c['ResourceChange'].get(k) for k in ('Action','LogicalResourceId','ResourceType','Replacement')} for c in detail.get('Changes',[])]}
        args.manifest.write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8');print(json.dumps(manifest));return
    manifest=json.loads(args.manifest.read_text(encoding='utf-8'))
    if manifest['review_sha256']!=review_hash or manifest['template_sha256']!=digest(args.template) or manifest['region']!=args.region:raise ValueError('Review, template or Region changed; recreate changeset')
    if manifest.get('status')=='NO_CHANGES':print('NO_CHANGES');return
    detail=cf.describe_change_set(ChangeSetName=manifest['change_set_id'])
    if detail['Description']!='CloudHub hosting reviewed '+review_hash or detail['StackId']!=manifest['stack_id']:raise ValueError('Changeset does not belong to this review')
    if completed(detail):print('ALREADY_EXECUTED');return
    baseline=None
    if manifest['kind']=='UPDATE':
        baseline=cf.get_template(StackName=manifest['stack_id'],TemplateStage='Original')['TemplateBody']
        if isinstance(baseline,str):baseline=json.loads(baseline)
    validate_changes(detail,t,manifest['kind'],baseline)
    previous={v['ParameterKey']:v for v in cf.describe_stacks(StackName=manifest['stack_id'])['Stacks'][0].get('Parameters',[])}
    proposed={p['ParameterKey']:p['ParameterValue'] for p in detail.get('Parameters',[]) if 'ParameterValue' in p}
    certificate_guard(session,t,proposed,previous,review['account_id'],args.region)
    if any(c['ResourceChange']['Action']=='Remove' for c in detail.get('Changes',[])):
        original=cf.get_template(StackName=manifest['stack_id'],TemplateStage='Original')['TemplateBody']
        if isinstance(original,str):original=json.loads(original)
        for c in detail['Changes']:
            v=c['ResourceChange']
            if v['Action']=='Remove' and original['Resources'][v['LogicalResourceId']].get('DeletionPolicy')!='Retain':
                raise ValueError('Deploy 00-retain first; source removal is unsafe')
    cf.update_termination_protection(StackName=manifest['stack_id'],EnableTerminationProtection=True)
    cf.execute_change_set(ChangeSetName=manifest['change_set_id'])
    cf.get_waiter({'CREATE':'stack_create_complete','UPDATE':'stack_update_complete','IMPORT':'stack_import_complete'}[manifest['kind']]).wait(StackName=manifest['stack_id'],WaiterConfig={'Delay':15,'MaxAttempts':120})
    print(json.dumps({'status':'STACK_COMPLETE','stack_id':manifest['stack_id'],'region':args.region,'dns_and_auth_acceptance_still_required':True}))

if __name__=='__main__':main()
