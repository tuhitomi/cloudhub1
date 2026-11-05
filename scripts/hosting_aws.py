"""Bounded AWS reads for hosting review; no credentials or edge key in outputs."""
import json
from datetime import datetime,timezone
from botocore.config import Config
from hosting import select_zone,check_certificate

def inspect(session,c,stack_name):
    region=c['PRIMARY_REGION'];cache={}
    def client(service,r=region):
        if (service,r) not in cache:cache[service,r]=session.client(service,region_name=r,config=Config(connect_timeout=5,read_timeout=15,retries={'total_max_attempts':3}))
        return cache[service,r]
    account=client('sts').get_caller_identity()['Account']
    if account!=c['ACCOUNT_ID']:raise ValueError('Wrong AWS account')
    cf=client('cloudformation');stack=cf.describe_stacks(StackName=stack_name)['Stacks'][0]
    if stack['StackStatus'] not in ('CREATE_COMPLETE','UPDATE_COMPLETE'):raise ValueError('Source stack is not stable')
    out={v['OutputKey']:v['OutputValue'] for v in stack['Outputs']}
    f=client('cloudfront').get_distribution(Id=out['DistributionId'])['Distribution'];d=f['DistributionConfig']
    api_id=cf.describe_stack_resource(StackName=stack_name,LogicalResourceId='HttpApi')['StackResourceDetail']['PhysicalResourceId']
    api=client('apigatewayv2').get_api(ApiId=api_id)
    uc=client('cognito-idp',c['COGNITO_REGION']).describe_user_pool_client(UserPoolId=out['UserPoolId'],ClientId=out['ClientId'])['UserPoolClient']
    edge_ids={}
    edge_stack=c.get('SHARED_EDGE_STACK_NAME') or stack_name
    edge_cf=client('cloudformation',c.get('SHARED_STACK_REGION',region))
    for name in ('FrontendDistribution','OriginAccess','UiCountryOriginPolicy'):
        edge_ids[name]=edge_cf.describe_stack_resource(StackName=edge_stack,LogicalResourceId=name)['StackResourceDetail']['PhysicalResourceId']
    zones=[]
    for page in client('route53').get_paginator('list_hosted_zones').paginate():
        zones.extend({'id':z['Id'].split('/')[-1],'name':z['Name'],'private':z['Config']['PrivateZone']} for z in page['HostedZones'])
    certs=[]
    for r in sorted({'us-east-1',region}):
        for page in client('acm',r).get_paginator('list_certificates').paginate():
            certs.extend({'region':r,'arn':v['CertificateArn'],'domain':v['DomainName'],'status':v.get('Status')} for v in page['CertificateSummaryList'])
    result={'recorded_at':datetime.now(timezone.utc).isoformat(),'mode':'AWS_READ_ONLY','account_id':account,'primary_region':region,
        'stack_name':stack_name,'stack_status':stack['StackStatus'],'edge_resource_ids':edge_ids,'edge_stack_name':edge_stack,'edge_stack_region':c.get('SHARED_STACK_REGION',region),
        'frontend':{'bucket':out['FrontendBucket'],'distribution_id':f['Id'],'distribution_domain':f['DomainName'],'status':f['Status'],
            'aliases':d.get('Aliases',{}).get('Items',[]),'ipv6_enabled':d.get('IsIPV6Enabled',False),
            'origins':[{'id':v['Id'],'domain':v['DomainName'],'oac_id':v.get('OriginAccessControlId'),'origin_path':v.get('OriginPath',''),
                'custom_header_names':[h['HeaderName'] for h in v.get('CustomHeaders',{}).get('Items',[])]} for v in d['Origins']['Items']],
            's3_block_public_access':client('s3').get_public_access_block(Bucket=out['FrontendBucket'])['PublicAccessBlockConfiguration'],
            's3_policy_status':client('s3').get_bucket_policy_status(Bucket=out['FrontendBucket'])['PolicyStatus']},
        'api':{'id':api_id,'endpoint':api['ApiEndpoint'],'cors':api.get('CorsConfiguration'),
            'stages':[v['StageName'] for v in client('apigatewayv2').get_stages(ApiId=api_id)['Items']],
            'authorizers':[{k:v.get(k) for k in ('Name','AuthorizerType','JwtConfiguration')} for v in client('apigatewayv2').get_authorizers(ApiId=api_id).get('Items',[])]},
        'cognito':{'region':c['COGNITO_REGION'],'pool_id':out['UserPoolId'],'client_id':out['ClientId'],'hosted_domain':out['CognitoDomain'],
            **{k:uc.get(k) for k in ('CallbackURLs','LogoutURLs','ExplicitAuthFlows','AllowedOAuthFlows','AllowedOAuthScopes')}},
        'hosted_zones':zones,'certificates':certs,'domain_changes_made':False,'paid_resources_created':False}
    if out.get('FrontendOriginDomain'):result['target_frontend_origin']=out['FrontendOriginDomain']
    if c.get('DNS_PROVIDER')=='route53' and c.get('ROOT_DOMAIN'):
        z=select_zone(zones,c);detail=client('route53').get_hosted_zone(Id=z['id'])
        result['selected_zone']={**z,'nameservers':detail.get('DelegationSet',{}).get('NameServers',[]),'public_delegation_verified':False}
        records=[]
        for name in dict.fromkeys([c['FRONTEND_DOMAIN'],c['API_DOMAIN'],c.get('REDIRECT_DOMAIN')]):
            if not name:continue
            for typ in ('A','AAAA') if c.get('IPV6_ENABLED') and name!=c['API_DOMAIN'] else ('A',):
                page=client('route53').list_resource_record_sets(HostedZoneId=z['id'],StartRecordName=name,StartRecordType=typ,MaxItems='1')
                records.extend(v for v in page['ResourceRecordSets'] if v['Name'].rstrip('.').lower()==name and v['Type']==typ)
        result['selected_zone']['records']=records
    if c.get('API_DOMAIN'):
        try:
            domain=client('apigatewayv2').get_domain_name(DomainName=c['API_DOMAIN']);dc=domain['DomainNameConfigurations'][0]
            result['api']['custom_domain']={'domain':domain['DomainName'],'target':dc['ApiGatewayDomainName'],'target_zone':dc['HostedZoneId'],
                'security_policy':dc.get('SecurityPolicy'),'status':dc['DomainNameStatus'],
                'mappings':[{k:m.get(k,'') for k in ('ApiId','ApiMappingKey','Stage')} for m in client('apigatewayv2').get_api_mappings(DomainName=c['API_DOMAIN']).get('Items',[])]}
        except client('apigatewayv2').exceptions.NotFoundException:result['api']['custom_domain']=None
    for key,front in [('FRONTEND_CERTIFICATE_ARN',True),('API_CERTIFICATE_ARN',False)]:
        if c.get(key):
            r='us-east-1' if front else region
            detail=client('acm',r).describe_certificate(CertificateArn=c[key])['Certificate']
            check_certificate(detail,c,front)
    source=cf.get_template(StackName=stack_name,TemplateStage='Original')['TemplateBody']
    if isinstance(source,str):source=json.loads(source)
    return result,source

def validation_records(acm,arn):
    """Actual CNAMEs only; never synthesize ACM tokens before requesting a cert."""
    value=acm.describe_certificate(CertificateArn=arn)['Certificate']
    rows=[]
    for item in value.get('DomainValidationOptions',[]):
        if item.get('ResourceRecord') and item['ResourceRecord'] not in rows:rows.append(item['ResourceRecord'])
    return {'certificate_arn':arn,'status':value['Status'],'records':rows,'keep_for_renewal':True,'complete':value['Status']=='ISSUED'}
