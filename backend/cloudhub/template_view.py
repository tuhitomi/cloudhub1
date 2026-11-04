"""Read the exact owned stack, then expose a fail-closed educational projection.

Never returns raw templates, stack parameters, bootstrap, code or environment.
No reconstruction from current builders: absent AWS templates remain absent.
"""
import hashlib
import json
import re
from botocore.exceptions import BotoCoreError, ClientError
from .errors import HubError

HIDDEN = '[REDACTED]'
MAX_BYTES = 1024 * 1024
ID = r'[A-Za-z][A-Za-z0-9]{0,254}'
TYPE = r'AWS::[A-Za-z0-9]+::[A-Za-z0-9]+'

# An explicit structural allowlist is safer than guessing which arbitrary
# strings might be passwords. New/unknown properties remain hidden by default.
NUMBER = r'\d+(?:\.\d+)?'
BOOL = r'(?:true|false)'
NET_ID = r'(?:ami|subnet|sg|vpc|vol)-[a-f0-9]{8,32}'
EBS = {'VolumeSize': NUMBER, 'VolumeType': r'(?:gp2|gp3|io1|io2|standard)',
       'Encrypted': BOOL, 'DeleteOnTermination': BOOL, 'Iops': NUMBER, 'Throughput': NUMBER}
NET = {'DeviceIndex': NUMBER, 'AssociatePublicIpAddress': BOOL, 'SubnetId': NET_ID,
       'GroupSet': [NET_ID], 'DeleteOnTermination': BOOL}
RULE = {'IpProtocol': r'(?:tcp|udp|icmp|icmpv6|-1)', 'FromPort': NUMBER, 'ToPort': NUMBER,
        'SourceSecurityGroupId': NET_ID, 'DestinationSecurityGroupId': NET_ID,
        'CidrIp': r'(?:\d{1,3}\.){3}\d{1,3}/\d{1,2}'}
SPECS = {
    'AWS::EC2::Instance': {'InstanceType': r'[a-z][a-z0-9-]*\.[a-z0-9]+', 'ImageId': NET_ID,
        'SubnetId': NET_ID, 'SecurityGroupIds': [NET_ID], 'NetworkInterfaces': [NET],
        'BlockDeviceMappings': [{'DeviceName': r'/dev/[A-Za-z0-9]+', 'Ebs': EBS}],
        'MetadataOptions': {'HttpTokens': r'(?:required|optional)'},
        'CreditSpecification': {'CPUCredits': r'(?:standard|unlimited)'}},
    'AWS::EC2::Volume': {'Size': NUMBER, 'VolumeType': EBS['VolumeType'], 'Encrypted': BOOL,
        'Iops': NUMBER, 'Throughput': NUMBER, 'AvailabilityZone': r'[a-z]{2}-[a-z]+-\d[a-z]'},
    'AWS::EC2::VolumeAttachment': {'InstanceId': NET_ID, 'VolumeId': NET_ID, 'Device': r'/dev/[A-Za-z0-9]+'},
    'AWS::EC2::SecurityGroup': {'VpcId': NET_ID, 'SecurityGroupIngress': [RULE], 'SecurityGroupEgress': [RULE]},
    'AWS::RDS::DBInstance': {'DBInstanceClass': r'db\.[a-z0-9]+\.[a-z0-9]+',
        'AllocatedStorage': NUMBER, 'Engine': r'(?:postgres|mysql|mariadb|aurora-postgresql)',
        'EngineVersion': r'\d+(?:\.\d+){0,2}', 'StorageType': EBS['VolumeType'],
        'StorageEncrypted': BOOL, 'MultiAZ': BOOL, 'PubliclyAccessible': BOOL,
        'VPCSecurityGroups': [NET_ID], 'DBSubnetGroupName': r'cloudhub-[a-z0-9-]+',
        'BackupRetentionPeriod': NUMBER, 'DeletionProtection': BOOL},
    'AWS::RDS::DBSubnetGroup': {'SubnetIds': [NET_ID]},
    'AWS::AutoScaling::AutoScalingGroup': {'MinSize': NUMBER, 'MaxSize': NUMBER,
        'DesiredCapacity': NUMBER, 'VPCZoneIdentifier': [NET_ID],
        'HealthCheckType': r'(?:EC2|ELB)', 'HealthCheckGracePeriod': NUMBER,
        'LaunchTemplate': {'LaunchTemplateId': r'lt-[a-f0-9]+', 'Version': r'(?:\d+|\$Latest|\$Default)'},
        'TargetGroupARNs': [r'arn:aws:elasticloadbalancing:[a-z0-9-]+:\d{12}:targetgroup/[A-Za-z0-9/-]+']},
    'AWS::EC2::LaunchTemplate': {'LaunchTemplateData': {
        'InstanceType': r'[a-z][a-z0-9-]*\.[a-z0-9]+', 'ImageId': NET_ID,
        'SecurityGroupIds': [NET_ID], 'NetworkInterfaces': [NET],
        'BlockDeviceMappings': [{'DeviceName': r'/dev/[A-Za-z0-9]+', 'Ebs': EBS}]}},
    'AWS::ElasticLoadBalancingV2::LoadBalancer': {'Type': r'(?:application|network)',
        'Scheme': r'(?:internet-facing|internal)', 'Subnets': [NET_ID], 'SecurityGroups': [NET_ID]},
    'AWS::ElasticLoadBalancingV2::TargetGroup': {'Port': NUMBER, 'Protocol': r'(?:HTTP|HTTPS|TCP)',
        'TargetType': r'(?:instance|ip|lambda)', 'VpcId': NET_ID, 'HealthCheckIntervalSeconds': NUMBER},
    'AWS::ECS::TaskDefinition': {'Cpu': NUMBER, 'Memory': NUMBER,
        'NetworkMode': r'(?:awsvpc|bridge|host|none)', 'RequiresCompatibilities': [r'(?:FARGATE|EC2)']},
    'AWS::ECS::Service': {'DesiredCount': NUMBER, 'LaunchType': r'(?:FARGATE|EC2)',
        'Cluster': r'arn:aws:ecs:[a-z0-9-]+:\d{12}:cluster/cloudhub-[a-z0-9-]+',
        'TaskDefinition': r'arn:aws:ecs:[a-z0-9-]+:\d{12}:task-definition/cloudhub-[a-z0-9:-]+'},
    'AWS::EFS::FileSystem': {'Encrypted': BOOL, 'PerformanceMode': r'(?:generalPurpose|maxIO)',
        'ThroughputMode': r'(?:bursting|provisioned|elastic)', 'ProvisionedThroughputInMibps': NUMBER},
    'AWS::EFS::MountTarget': {'FileSystemId': r'fs-[a-f0-9]+', 'SubnetId': NET_ID, 'SecurityGroups': [NET_ID]},
    'AWS::S3::Bucket': {'VersioningConfiguration': {'Status': r'(?:Enabled|Suspended)'},
        'PublicAccessBlockConfiguration': {k: BOOL for k in ('BlockPublicAcls','BlockPublicPolicy','IgnorePublicAcls','RestrictPublicBuckets')},
        'BucketEncryption': {'ServerSideEncryptionConfiguration': [{'ServerSideEncryptionByDefault': {'SSEAlgorithm': r'(?:AES256|aws:kms)'}}]}},
    'AWS::CloudFront::Distribution': {'DistributionConfig': {'Enabled': BOOL,
        'HttpVersion': r'(?:http1.1|http2|http2and3|http3)', 'PriceClass': r'PriceClass_(?:100|200|All)',
        'DefaultCacheBehavior': {'ViewerProtocolPolicy': r'(?:redirect-to-https|https-only|allow-all)',
            'AllowedMethods': [r'(?:GET|HEAD|OPTIONS|PUT|POST|PATCH|DELETE)'], 'Compress': BOOL}}},
    'AWS::DynamoDB::Table': {'BillingMode': r'(?:PAY_PER_REQUEST|PROVISIONED)',
        'AttributeDefinitions': [{'AttributeName': ID, 'AttributeType': r'(?:S|N|B)'}],
        'KeySchema': [{'AttributeName': ID, 'KeyType': r'(?:HASH|RANGE)'}],
        'ProvisionedThroughput': {'ReadCapacityUnits': NUMBER, 'WriteCapacityUnits': NUMBER}},
    'AWS::Lambda::Function': {'Runtime': r'(?:python|nodejs|java|dotnet)[a-z0-9.]+',
        'MemorySize': NUMBER, 'Timeout': NUMBER, 'Architectures': [r'(?:x86_64|arm64)'],
        'ReservedConcurrentExecutions': NUMBER},
    'AWS::ApiGatewayV2::Api': {'ProtocolType': r'(?:HTTP|WEBSOCKET)', 'DisableExecuteApiEndpoint': BOOL},
    'AWS::Logs::LogGroup': {'RetentionInDays': NUMBER},
}

def projection(source):
    """Return only reviewed shape; never expose arbitrary code, defaults or text."""
    if not isinstance(source, dict) or not isinstance(source.get('Resources'), dict) or len(source['Resources']) > 200:
        raise HubError('TEMPLATE_FORMAT_UNSUPPORTED', 'Template cannot be safely displayed.', 409)
    resources = source['Resources']; valid = set(resources)
    params = {k for k in source.get('Parameters', {}) if re.fullmatch(ID, k)}
    redactions = 0
    def hide():
        nonlocal redactions
        redactions += 1
        return HIDDEN
    def value(raw, spec, depth=0):
        if depth > 24:return hide()
        if isinstance(raw, dict):
            if set(raw) == {'Ref'} and isinstance(raw['Ref'], str) and raw['Ref'] in valid | params | {'AWS::Region','AWS::AccountId','AWS::Partition'}:
                return {'Ref': raw['Ref']}
            if set(raw) == {'Fn::GetAtt'}:
                target = raw['Fn::GetAtt']; target = target.split('.',1) if isinstance(target,str) else target
                if isinstance(target,list) and len(target)==2 and target[0] in valid and isinstance(target[1],str) and re.fullmatch(ID,target[1]):
                    return {'Fn::GetAtt': target}
            if isinstance(spec, dict):
                return {k: value(v, spec[k], depth+1) if k in spec else hide() for k,v in raw.items() if re.fullmatch(ID,k)}
            return hide()
        if isinstance(raw,list) and isinstance(spec,list) and len(raw)<=200:
            return [value(v,spec[0],depth+1) for v in raw]
        text = str(raw).lower() if isinstance(raw,bool) else str(raw)
        if isinstance(spec,str) and type(raw) in {str,int,float,bool} and re.fullmatch(spec,text):return raw
        return hide()
    result = {'AWSTemplateFormatVersion':'2010-09-09','Resources':{}}
    summaries=[]
    for logical,row in resources.items():
        if not re.fullmatch(ID,logical) or not isinstance(row,dict) or not re.fullmatch(TYPE,str(row.get('Type',''))):
            raise HubError('TEMPLATE_FORMAT_UNSUPPORTED','Template cannot be safely displayed.',409)
        rtype=row['Type']; rendered={'Type':rtype}
        if 'Properties' in row:rendered['Properties']=value(row['Properties'], SPECS.get(rtype, {}))
        deps=row.get('DependsOn',[]);deps=[deps] if isinstance(deps,str) else deps
        if isinstance(deps,list) and deps and all(isinstance(d,str) and d in valid for d in deps):rendered['DependsOn']=deps
        for field in ('DeletionPolicy','UpdateReplacePolicy'):
            if row.get(field) in ('Delete','Retain','RetainExceptOnCreate','Snapshot'):rendered[field]=row[field]
        result['Resources'][logical]=rendered
        summaries.append({'logical_id':logical,'resource_type':rtype,'service':rtype.split('::')[1]})
    # Defaults, metadata, outputs, mappings, conditions and parameter values may
    # contain secrets even when NoEcho is set. Never include those values.
    if params:
        result['Parameters']={k:{'Type':source['Parameters'][k].get('Type','String'),'NoEcho':True} for k in sorted(params)
            if isinstance(source['Parameters'][k],dict) and source['Parameters'][k].get('Type') in ('String','Number','List<Number>','CommaDelimitedList')}
        redactions+=len(params)
    omitted=[k for k in ('Description','Metadata','Mappings','Outputs','Conditions','Transform','Rules') if k in source]
    redactions+=len(omitted)+sum('Metadata' in r for r in resources.values())
    return result,summaries,redactions,omitted

def read(service, owner, eid, settings=None, client=None):
    env=service.owned('E',eid,owner)  # Must happen before config or any SDK call.
    if not re.fullmatch(r'env-[a-f0-9]{24}',eid) or env.get('template_id') not in {f'T{i:02}' for i in range(1,10)}:
        raise HubError('TEMPLATE_UNAVAILABLE','No managed template for this environment.',409)
    region=service.region_for(env)
    if settings is None:
        from .runtime import driver_settings
        settings=driver_settings()
    account=settings.get('account_id','')
    if not re.fullmatch(r'\d{12}',account):raise HubError('TEMPLATE_UNAVAILABLE','Template settings are unavailable.',503)
    expected='cloudhub-'+eid
    prefix=f'arn:aws:cloudformation:{region}:{account}:stack/{expected}/'
    # Stored ARN is required for deleted stacks, and is validated before use.
    saved=env.get('stack_id')
    if saved and (not isinstance(saved,str) or not saved.startswith(prefix) or not re.fullmatch(r'[A-Za-z0-9-]+',saved[len(prefix):])):
        raise HubError('RESOURCE_SCOPE_MISMATCH','Stack provenance does not match this environment.',409)
    target=saved or expected
    if client is None:
        import boto3
        from botocore.config import Config
        client=boto3.client('cloudformation',region_name=region,config=Config(connect_timeout=2,read_timeout=5,retries={'total_max_attempts':1}))
    try:
        rows=client.describe_stacks(StackName=target).get('Stacks',[])
        if len(rows)!=1:raise HubError('TEMPLATE_UNAVAILABLE','The stack is not available.',404)
        stack=rows[0];tags={t['Key']:t['Value'] for t in stack.get('Tags',[])}
        if stack.get('StackName')!=expected or not stack.get('StackId','').startswith(prefix) or any(tags.get('cloudhub:'+k)!=v for k,v in [('environment',eid),('owner',owner)]):
            raise HubError('RESOURCE_SCOPE_MISMATCH','Stack ownership could not be verified.',409)
        original=client.get_template(StackName=stack['StackId'],TemplateStage='Original')['TemplateBody']
    except ClientError as exc:
        code=exc.response.get('Error',{}).get('Code','')
        if code=='ValidationError':raise HubError('TEMPLATE_UNAVAILABLE','AWS no longer provides this stack template.',404) from None
        if code in ('AccessDenied','AccessDeniedException','UnauthorizedOperation'):
            raise HubError('TEMPLATE_ACCESS_UNAVAILABLE','The service cannot read this template yet.',503) from None
        raise HubError('TEMPLATE_TEMPORARILY_UNAVAILABLE','Template service is temporarily unavailable.',503) from None
    except BotoCoreError:
        raise HubError('TEMPLATE_TEMPORARILY_UNAVAILABLE','Template service is temporarily unavailable.',503) from None
    try:
        raw=json.dumps(original,ensure_ascii=False).encode() if isinstance(original,dict) else original.encode()
        if len(raw)>MAX_BYTES:raise ValueError('too large')
        document=json.loads(original) if isinstance(original,str) else original
        template,resources,count,omitted=projection(document)
    except (ValueError,TypeError,AttributeError,RecursionError):
        raise HubError('TEMPLATE_FORMAT_UNSUPPORTED','Template cannot be safely displayed.',409) from None
    canonical=json.dumps(template,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    return {'environment_id':eid,'template_id':env['template_id'],'region':region,
        'source':'AWS_CLOUDFORMATION_ORIGINAL','read_only':True,'redacted':True,'deployable':False,
        'retrieved_at':int(service.clock()),'view_sha256':hashlib.sha256(canonical).hexdigest(),
        'template':template,'resources':resources,'redaction_count':count,'omitted_sections':omitted,
        'scope':'DECLARED_STACK_NOT_LIVE_INVENTORY'}
