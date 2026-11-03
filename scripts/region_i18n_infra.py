"""Extend SAM with fail-closed Region gates and a private country route."""
def regional_t07_permissions(resources,ref,sub):
    """Separate opt-in managed policies keep existing policies below IAM size limits.
    Only S3/CloudFormation operations needed by T07; no compute or snapshot grants.
    Generated SAM role IDs are documented referenceable CloudFormation resources.
    """
    regions=('ap-northeast-1','us-east-1')
    bucket=[sub('arn:${AWS::Partition}:s3:::cloudhub-${AWS::AccountId}-'+r+'-*') for r in regions]
    objects=[sub('arn:${AWS::Partition}:s3:::cloudhub-${AWS::AccountId}-'+r+'-*/*') for r in regions]
    backup=[sub('arn:${AWS::Partition}:s3:::cloudhub-${AWS::AccountId}-'+r+'-backup') for r in regions]
    def statement(actions,arns,condition=None):
        result={'Effect':'Allow','Action':actions,'Resource':arns}
        if condition:result['Condition']=condition
        return result
    env=[statement(['s3:CreateBucket','s3:DeleteBucket','s3:GetBucketLocation','s3:GetBucketTagging','s3:PutBucketTagging',
        's3:GetBucketVersioning','s3:PutBucketVersioning','s3:GetBucketPublicAccessBlock','s3:PutBucketPublicAccessBlock',
        's3:GetEncryptionConfiguration','s3:PutEncryptionConfiguration','s3:GetBucketOwnershipControls','s3:PutBucketOwnershipControls',
        's3:GetBucketPolicy','s3:PutBucketPolicy','s3:DeleteBucketPolicy','s3:ListBucket'],bucket)]
    worker=[statement(['cloudformation:CreateStack','cloudformation:DeleteStack','cloudformation:DescribeStacks','cloudformation:ListStackResources'],
        [sub('arn:${AWS::Partition}:cloudformation:'+r+':${AWS::AccountId}:stack/cloudhub-env-*/*') for r in regions]),
        statement(['s3:GetBucketTagging','s3:ListBucket','s3:ListBucketVersions','s3:GetBucketPolicy'],bucket),
        statement(['s3:GetObject','s3:GetObjectVersion','s3:PutObject','s3:DeleteObject','s3:DeleteObjectVersion'],objects),
        statement('s3:ListBucket',backup,{'StringLike':{'s3:prefix':'recovery/rp-*/*'}}),
        statement(['s3:GetObject','s3:PutObject','s3:DeleteObject'],[sub('arn:${AWS::Partition}:s3:::cloudhub-${AWS::AccountId}-'+r+'-backup/recovery/rp-*/*') for r in regions])]
    api=[statement(['s3:GetBucketTagging','s3:ListBucket'],bucket),statement(['s3:GetObject','s3:GetObjectVersion'],objects),
        statement('s3:GetObject',[sub('arn:${AWS::Partition}:s3:::cloudhub-${AWS::AccountId}-'+r+'-backup/recovery/rp-*/exports/*') for r in regions])]
    for name,roles,statements in [('RegionalS3EnvironmentPolicy',['EnvironmentCfRole'],env),('RegionalS3WorkerPolicy',['WorkerFunctionRole','SweepFunctionRole'],worker),('RegionalS3ApiPolicy',['ApiFunctionRole'],api)]:
        resources[name]={'Type':'AWS::IAM::ManagedPolicy','Condition':'HasRegionalT07','Properties':{'Roles':[ref(r) for r in roles],
            'PolicyDocument':{'Version':'2012-10-17','Statement':statements}}}

def extend(params,resources,common,ref,sub,att,external=False):
    params['EnableRegionalT07']={'Type':'String','Default':'false','AllowedValues':['false','true'],
        'Description':'Opt in to reviewed T07-only S3 permissions in Tokyo/Virginia. Does not enable template verification gates.'}
    regional_t07_permissions(resources,ref,sub)
    conditions={'HasRegionalT07':{'Fn::Equals':[ref('EnableRegionalT07'),'true']}}
    params['RegionsJson']={'Type':'String','Default':'{"regions":{}}','Description':'Operator-reviewed Region matrix. New Regions default disabled.'}
    params['DriverRegionsJson']={'Type':'String','Default':'{}','Description':'Explicit regional AMI/network/backup profiles; no home identifiers inherited.'}
    for key in ('RegionsParameter','DriverRegionsParameter'):
        params[key]={'Type':'String','Default':'','AllowedPattern':'(|/cloudhub/[A-Za-z0-9_-]+/regions/[A-Za-z0-9_/-]+)','Description':'Optional control-Region SSM Standard parameter, replaces inline JSON.'}
    params['RegionalPricesParametersJson']={'Type':'String','Default':'{}','Description':'Region to control-Region SSM Standard price parameter path. Each Region has separate prices.'}
    params['UiEdgeSecret']={'Type':'String','NoEcho':True,'MinLength':32,'MaxLength':128,'AllowedPattern':'[A-Za-z0-9_-]{32,128}','Description':'Random origin-only secret. Never include in public config or logs.'}
    params['UiApiOriginDomain']={'Type':'String','Default':'','AllowedPattern':'(|[a-z0-9]+\\.execute-api\\.[a-z]{2}-[a-z]+-[0-9]\\.amazonaws\\.com)','Description':'Existing API hostname from ApiUrl output. Set after initial creation to avoid Cognito/CloudFront dependency cycle.'}
    for name in ('ApiFunction','WorkerFunction','SweepFunction','ExpiryFunction'):
        env=resources[name]['Properties']['Environment']['Variables']
        env.update(REGIONS_JSON=ref('RegionsJson'),DRIVER_REGIONS_JSON=ref('DriverRegionsJson'))
        env.update(REGIONS_PARAMETER=ref('RegionsParameter'),DRIVER_REGIONS_PARAMETER=ref('DriverRegionsParameter'),REGIONAL_PRICES_PARAMETERS_JSON=ref('RegionalPricesParametersJson'))
        resources[name]['Properties']['Policies'][0]['Statement'].append({'Effect':'Allow','Action':'ssm:GetParameter',
            'Resource':sub('arn:${AWS::Partition}:ssm:${AWS::Region}:${AWS::AccountId}:parameter/cloudhub/${AWS::StackName}/regions/*')})
    api=resources['ApiFunction']['Properties']
    api['Environment']['Variables']['UI_EDGE_SECRET']=ref('UiEdgeSecret')
    events=api['Events']
    for name,method,path in [('RegionCatalog','GET','/regions'),('LanguagePreference','PUT','/account/preferences'),('UiContext','GET','/ui-context'),('PublicCatalog','GET','/public/catalog')]:
        props={'ApiId':ref('HttpApi'),'Method':method,'Path':path}
        if name in {'UiContext','PublicCatalog'}:props['Auth']={'Authorizer':'NONE'}
        if name=='PublicCatalog':props['RouteSettings']={'ThrottlingBurstLimit':10,'ThrottlingRateLimit':5}
        events[name]={'Type':'HttpApi','Properties':props}
    cors=resources['HttpApi']['Properties']['CorsConfiguration']
    if 'PUT' not in cors['AllowMethods']:cors['AllowMethods'].append('PUT')
    if external:return conditions
    resources['UiCountryOriginPolicy']={'Type':'AWS::CloudFront::OriginRequestPolicy','Condition':'HasUiContextOrigin','Properties':{'OriginRequestPolicyConfig':{
        'Name':sub('${AWS::StackName}-ui-country'),'Comment':'Generated country only; no viewer Host, auth or cookies',
        'CookiesConfig':{'CookieBehavior':'none'},'QueryStringsConfig':{'QueryStringBehavior':'none'},
        'HeadersConfig':{'HeaderBehavior':'whitelist','Headers':['CloudFront-Viewer-Country']}}}}
    distribution=resources['FrontendDistribution']['Properties']['DistributionConfig']
    distribution['Origins'].append({'Fn::If':['HasUiContextOrigin',{'Id':'ui-context-api','DomainName':ref('UiApiOriginDomain'),
        'CustomOriginConfig':{'OriginProtocolPolicy':'https-only','OriginSSLProtocols':['TLSv1.2']},
        'OriginCustomHeaders':[{'HeaderName':'X-CloudHub-Edge-Key','HeaderValue':ref('UiEdgeSecret')}]},ref('AWS::NoValue')]})
    distribution.setdefault('CacheBehaviors',[]).append({'Fn::If':['HasUiContextOrigin',{'PathPattern':'/ui-context','TargetOriginId':'ui-context-api','ViewerProtocolPolicy':'https-only',
        'AllowedMethods':['GET','HEAD'],'CachedMethods':['GET','HEAD'],'Compress':True,
        'CachePolicyId':'4135ea2d-6df8-44a3-9df3-4b5a84be39ad','OriginRequestPolicyId':ref('UiCountryOriginPolicy')},ref('AWS::NoValue')]})
    conditions['HasUiContextOrigin']={'Fn::Not':[{'Fn::Equals':[ref('UiApiOriginDomain'),'']}]}
    return conditions
