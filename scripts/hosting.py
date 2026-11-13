"""Pure configuration and CloudFormation transformations for stable public URLs.

No AWS calls. Existing edge resources are adopted, never recreated for an alias.
The DNS stack is shared; an old regional API stack never owns the public records.
"""
from copy import deepcopy
import ipaddress,json,re
from urllib.parse import urlsplit

EDGE_TYPES={'AWS::CloudFront::Distribution','AWS::CloudFront::OriginAccessControl','AWS::CloudFront::OriginRequestPolicy'}
PROTECTED_TYPES=EDGE_TYPES|{'AWS::S3::Bucket','AWS::S3::BucketPolicy','AWS::DynamoDB::Table','AWS::Backup::BackupVault',
 'AWS::Cognito::UserPool','AWS::Cognito::UserPoolClient','AWS::Cognito::UserPoolDomain','AWS::Cognito::UserPoolGroup','AWS::Cognito::UserPoolResourceServer',
 'AWS::CertificateManager::Certificate','AWS::Route53::RecordSet','AWS::Route53::HostedZone','AWS::ApiGatewayV2::DomainName','AWS::ApiGatewayV2::ApiMapping','AWS::CloudFront::Function'}
CF_ZONE='Z2FDTNDATAQYW2'
DISABLED_CACHE='4135ea2d-6df8-44a3-9df3-4b5a84be39ad'

def host(value):
    if not isinstance(value,str) or value!=value.strip() or any(c in value for c in '/:@?#*\\'):
        raise ValueError('Expected a hostname, without URL, wildcard, whitespace or port')
    try:v=value.rstrip('.').encode('idna').decode('ascii').lower()
    except UnicodeError:raise ValueError('Invalid hostname') from None
    if len(v)>253 or len(v.split('.'))<2 or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',x) for x in v.split('.')):
        raise ValueError('Invalid fully-qualified hostname')
    try:ipaddress.ip_address(v)
    except ValueError:return v
    raise ValueError('An IP address is not a domain')

def under(name,root):return name==root or name.endswith('.'+root)

def certificate_arn(value,account,region):
    if not re.fullmatch(r'arn:aws:acm:'+re.escape(region)+':'+re.escape(account)+r':certificate/[A-Za-z0-9-]+',value):
        raise ValueError('ACM certificate must belong to the configured account and Region: '+region)
    return value

def config(value):
    c=deepcopy(value)
    if not re.fullmatch(r'\d{12}',str(c.get('ACCOUNT_ID',''))):raise ValueError('ACCOUNT_ID is required')
    for key in ('PRIMARY_REGION','SHARED_STACK_REGION','COGNITO_REGION'):
        if not re.fullmatch(r'[a-z]{2}-[a-z]+-\d',c.get(key,'')):raise ValueError(key+' is required')
    root=c['ROOT_DOMAIN']=host(c.get('ROOT_DOMAIN',''))
    for key in ('FRONTEND_DOMAIN','API_DOMAIN'):
        c[key]=host(c.get(key,''))
        if not under(c[key],root):raise ValueError(key+' must be within ROOT_DOMAIN')
    if c['FRONTEND_DOMAIN']==c['API_DOMAIN']:raise ValueError('Frontend and API need distinct hostnames')
    if c.get('REDIRECT_DOMAIN'):
        c['REDIRECT_DOMAIN']=host(c['REDIRECT_DOMAIN'])
        if c['REDIRECT_DOMAIN']!='www.'+root or c['REDIRECT_DOMAIN'] in (c['FRONTEND_DOMAIN'],c['API_DOMAIN']):
            raise ValueError('Optional redirect must be www.ROOT_DOMAIN and distinct from serving hosts')
    if c.get('DNS_PROVIDER') not in ('route53','external'):raise ValueError('DNS_PROVIDER must be route53 or external')
    zone=c.get('ROUTE53_HOSTED_ZONE_ID','')
    if c['DNS_PROVIDER']=='route53' and not re.fullmatch(r'Z[A-Z0-9]+',zone):raise ValueError('Explicit public hosted zone ID required')
    if c['DNS_PROVIDER']=='external' and zone:raise ValueError('External DNS cannot implicitly manage a Route 53 zone')
    if type(c.get('IPV6_ENABLED')) is not bool:raise ValueError('IPV6_ENABLED must be boolean')
    if not re.fullmatch(r'(\$default|[A-Za-z0-9_-]{1,128})',c.get('API_STAGE','')):raise ValueError('Invalid API_STAGE')
    if not re.fullmatch(r'[A-Za-z0-9_-]*(?:/[A-Za-z0-9_-]+)*',c.get('API_MAPPING_KEY','')):raise ValueError('Invalid API_MAPPING_KEY')
    for key,region in [('FRONTEND_CERTIFICATE_ARN','us-east-1'),('API_CERTIFICATE_ARN',c['PRIMARY_REGION'])]:
        if c.get(key):certificate_arn(c[key],c['ACCOUNT_ID'],region)
    origins=[]
    for value in c.get('TRANSITION_ORIGINS',[]):
        p=urlsplit(value)
        if p.scheme!='https' or p.username or p.password or p.port or p.path or p.query or p.fragment or p.netloc!=host(p.netloc):
            raise ValueError('Transition origins must be exact HTTPS origins')
        origins.append(value)
    c['TRANSITION_ORIGINS']=list(dict.fromkeys(origins))
    c['frontend_url']='https://'+c['FRONTEND_DOMAIN']+'/'
    c['api_url']='https://'+c['API_DOMAIN']+('/'+c['API_MAPPING_KEY'] if c['API_MAPPING_KEY'] else '')
    return c

def select_zone(zones,c):
    """Never infer a zone from a matching name; explicit ID plus public suffix check."""
    matches=[z for z in zones if z['id']==c['ROUTE53_HOSTED_ZONE_ID']]
    if len(matches)!=1 or matches[0]['private']:raise ValueError('Explicit zone is missing, ambiguous or private')
    z=matches[0];name=host(z['name'])
    if any(not under(h,name) for h in (c['FRONTEND_DOMAIN'],c['API_DOMAIN'],c.get('REDIRECT_DOMAIN') or c['FRONTEND_DOMAIN'])):
        raise ValueError('Hosted zone does not cover all configured names')
    return z

def covers(pattern,name):
    p=pattern.lower().rstrip('.')
    return p==name or p.startswith('*.') and name.endswith(p[1:]) and len(name.split('.'))==len(p.split('.'))

def check_certificate(detail,c,frontend):
    region='us-east-1' if frontend else c['PRIMARY_REGION']
    certificate_arn(detail['CertificateArn'],c['ACCOUNT_ID'],region)
    names=[c['FRONTEND_DOMAIN']]+([c['REDIRECT_DOMAIN']] if c.get('REDIRECT_DOMAIN') else []) if frontend else [c['API_DOMAIN']]
    sans=detail.get('SubjectAlternativeNames',[detail['DomainName']])
    if detail['Status']!='ISSUED' or any(not any(covers(s,n) for s in sans) for n in names):
        raise ValueError('Issued certificate does not cover every hostname')
    return detail['CertificateArn']

def retain(resource):
    resource['DeletionPolicy']=resource['UpdateReplacePolicy']='Retain';return resource

def template(resources,parameters=None,outputs=None,conditions=None):
    result={'AWSTemplateFormatVersion':'2010-09-09','Resources':resources}
    if parameters:result['Parameters']=parameters
    if outputs:result['Outputs']=outputs
    if conditions:result['Conditions']=conditions
    return result

def certificate_template(names,zone=''):
    props={'DomainName':names[0],'ValidationMethod':'DNS','CertificateTransparencyLoggingPreference':'ENABLED',
           'CertificateExport':'DISABLED'}
    if len(names)>1:props['SubjectAlternativeNames']=names[1:]
    if zone:props['DomainValidationOptions']=[{'DomainName':n,'HostedZoneId':zone} for n in names]
    return template({'Certificate':retain({'Type':'AWS::CertificateManager::Certificate','Properties':props})},
        outputs={'CertificateArn':{'Value':{'Ref':'Certificate'}}})

def hosted_zone_template(root):
    """Only for a reviewed missing PUBLIC zone; caller must inventory before CREATE."""
    name=host(root)
    return template({'PublicZone':retain({'Type':'AWS::Route53::HostedZone','Properties':{
        'Name':name,'HostedZoneConfig':{'Comment':'CloudHub shared public DNS; preserve on regional removal'},
        'HostedZoneTags':[{'Key':'project','Value':'CloudHub'}]}})},outputs={
        'HostedZoneId':{'Value':{'Ref':'PublicZone'}},
        'NameServers':{'Value':{'Fn::Join':[',',{'Fn::GetAtt':['PublicZone','NameServers']}]}}})

def api_template(c,api_id,stage=None):
    props={'DomainName':c['API_DOMAIN'],'DomainNameConfigurations':[{'CertificateArn':{'Ref':'CertificateArn'},'EndpointType':'REGIONAL','SecurityPolicy':'TLS_1_2'}]}
    mapping={'ApiId':api_id,'DomainName':{'Ref':'ApiDomain'},'Stage':stage or c['API_STAGE']}
    if c['API_MAPPING_KEY']:mapping['ApiMappingKey']=c['API_MAPPING_KEY']
    return template({'ApiDomain':retain({'Type':'AWS::ApiGatewayV2::DomainName','Properties':props}),
        'ApiMapping':retain({'Type':'AWS::ApiGatewayV2::ApiMapping','Properties':mapping})},
        {'CertificateArn':{'Type':'String','Description':'Issued ACM certificate in this API Region'}},
        {'RegionalDomainName':{'Value':{'Fn::GetAtt':['ApiDomain','RegionalDomainName']}},
         'RegionalHostedZoneId':{'Value':{'Fn::GetAtt':['ApiDomain','RegionalHostedZoneId']}},'ApiUrl':{'Value':c['api_url']}})

def dns_template(c,distribution_domain,api_target=None):
    if c['DNS_PROVIDER']!='route53':return None
    params={'ApiTargetDomain':{'Type':'String'},'ApiTargetZone':{'Type':'String'}}
    r={}
    for prefix,name in [('Frontend',c['FRONTEND_DOMAIN']),('Redirect',c.get('REDIRECT_DOMAIN'))]:
        if not name:continue
        for typ in ('A','AAAA') if c['IPV6_ENABLED'] else ('A',):
            r[prefix+typ]=retain({'Type':'AWS::Route53::RecordSet','Properties':{'HostedZoneId':c['ROUTE53_HOSTED_ZONE_ID'],'Name':name+'.','Type':typ,
                'AliasTarget':{'DNSName':distribution_domain,'HostedZoneId':CF_ZONE,'EvaluateTargetHealth':False}}})
    r['ApiA']=retain({'Type':'AWS::Route53::RecordSet','Properties':{'HostedZoneId':c['ROUTE53_HOSTED_ZONE_ID'],'Name':c['API_DOMAIN']+'.','Type':'A',
        'AliasTarget':{'DNSName':{'Ref':'ApiTargetDomain'},'HostedZoneId':{'Ref':'ApiTargetZone'},'EvaluateTargetHealth':False}}})
    return template(r,params)

def external_records(c,distribution_domain,api_domain=None):
    result=[{'name':c['FRONTEND_DOMAIN'],'type':'ALIAS/ANAME' if c['FRONTEND_DOMAIN']==c['ROOT_DOMAIN'] else 'CNAME','value':distribution_domain,'proxy':False}]
    if c.get('REDIRECT_DOMAIN'):result.append({'name':c['REDIRECT_DOMAIN'],'type':'CNAME','value':distribution_domain,'proxy':False})
    result.append({'name':c['API_DOMAIN'],'type':'CNAME','value':api_domain,'pending':not bool(api_domain),'proxy':False})
    return result

def public_config(c,inventory):
    identity=inventory['cognito']
    if c['COGNITO_REGION']!=identity['region']:raise ValueError('Identity Region change requires a separate migration plan')
    return {'configured':True,'apiBase':c['api_url'],'redirectUri':c['frontend_url'],'region':identity['region'],
        'clientId':identity['client_id'],'cognitoDomain':identity['hosted_domain']}

def patch_regional(current,c):
    """Update existing auth URLs only; preserve JWT, identities, code and member edits."""
    result=deepcopy(current);r=result['Resources'];origin=c['frontend_url'].rstrip('/')
    client=r['UserClient']['Properties']
    for field in ('CallbackURLs','LogoutURLs'):
        client[field]=list(client.get(field,[]))
        for u in [c['frontend_url'],*[o+'/' for o in c['TRANSITION_ORIGINS']]]:
            if u not in client[field]:client[field].append(u)
    api=r['HttpApi']['Properties']
    if r['HttpApi']['Type']=='AWS::Serverless::HttpApi':cors=api['CorsConfiguration'];origins_key='AllowOrigins'
    elif r['HttpApi']['Type']=='AWS::ApiGatewayV2::Api' and 'Body' in api:
        cors=api['Body']['x-amazon-apigateway-cors'];origins_key='allowOrigins'
    else:raise ValueError('Unknown API CORS layout; preserve source for explicit review')
    cors[origins_key]=list(cors[origins_key])
    for o in [origin,*c['TRANSITION_ORIGINS']]:
        if o not in cors[origins_key]:cors[origins_key].append(o)
    if '*' in cors[origins_key]:raise ValueError('Wildcard CORS is not allowed')
    for resource in r.values():
        if resource['Type'] in PROTECTED_TYPES:retain(resource)
        variables=resource.get('Properties',{}).get('Environment',{}).get('Variables',{})
        settings=variables.get('DRIVER_SETTINGS')
        if settings is None:continue
        expression=settings.get('Fn::Sub') if isinstance(settings,dict) else None
        text=expression[0] if isinstance(expression,list) else expression
        if not isinstance(text,str):raise ValueError('Unknown driver settings expression; preserve source')
        parsed=json.loads(text);parsed['frontend_origin']=origin;text=json.dumps(parsed,separators=(',',':'))
        variables['DRIVER_SETTINGS']={'Fn::Sub':[text,deepcopy(expression[1])]} if isinstance(expression,list) else {'Fn::Sub':text}
    result['Outputs']['FrontendUrl']={'Value':c['frontend_url']}
    result['Outputs']['RawApiUrl']=deepcopy(result['Outputs'].get('RawApiUrl',result['Outputs']['ApiUrl']))
    result['Outputs']['ApiId']={'Value':{'Ref':'HttpApi'}}
    result['Outputs']['ApiUrl']={'Value':c['api_url']}
    result['Outputs']['IdentityRegion']={'Value':c['COGNITO_REGION']}
    return result

def split_edge(current,stack_name,inventory):
    """Prepare Retain -> detach -> IMPORT without property changes or new IDs.

    Must run in the source stack's Region. Import first, then change aliases/cert.
    Pass existing UiEdgeSecret privately as a NoEcho parameter, never in defaults.
    """
    original=deepcopy(current);r=original['Resources']
    names={n for n,v in r.items() if v['Type'] in EDGE_TYPES}
    if names!={'FrontendDistribution','OriginAccess','UiCountryOriginPolicy'}:raise ValueError('Unexpected edge layout; manual review required')
    protected=deepcopy(original)
    for v in protected['Resources'].values():
        if v['Type'] in PROTECTED_TYPES:retain(v)
    frontend=inventory['frontend'];s3=next(o for o in frontend['origins'] if o['id']=='private-s3')
    def edge_visit(v):
        if isinstance(v,list):return [edge_visit(x) for x in v]
        if not isinstance(v,dict):return v
        if v=={'Fn::GetAtt':['FrontendBucket','RegionalDomainName']}:return {'Ref':'OriginDomain'}
        if 'Fn::Sub' in v:
            text=v['Fn::Sub']
            if not isinstance(text,str):raise ValueError('Unknown edge substitution')
            text=text.replace('${AWS::StackName}',stack_name)
            return {'Fn::Sub':text} if '${' in text else text
        return {k:edge_visit(x) for k,x in v.items()}
    resources={n:retain(edge_visit(deepcopy(r[n]))) for n in sorted(names)}
    params={'UiEdgeSecret':deepcopy(current['Parameters']['UiEdgeSecret']),
            'UiApiOriginDomain':deepcopy(current['Parameters'].get('UiApiOriginDomain',{'Type':'String'}))}
    params['UiEdgeSecret'].pop('Default',None)
    params['OriginDomain']={'Type':'String','Description':'Explicit regional S3 REST endpoint; not a website endpoint'}
    for origin in resources['FrontendDistribution']['Properties']['DistributionConfig']['Origins']:
        body=origin['Fn::If'][1] if 'Fn::If' in origin else origin
        if body['Id']=='ui-context-api':body['DomainName']={'Ref':'UiApiOriginDomain'}
    conditions={k:deepcopy(v) for k,v in current.get('Conditions',{}).items() if k=='HasUiContextOrigin'}
    # CFN IMPORT forbids adding Outputs even when creating a new import stack.
    # Publish them in the subsequent, separately reviewed UPDATE instead.
    shared=template(resources,params,conditions=conditions)
    def detach_visit(v):
        if isinstance(v,str):return v.replace('${FrontendDistribution.DomainName}','${SharedDistributionDomain}').replace('${FrontendDistribution}','${SharedDistributionId}')
        if isinstance(v,list):return [detach_visit(x) for x in v]
        if not isinstance(v,dict):return v
        if v=={'Ref':'FrontendDistribution'}:return {'Ref':'SharedDistributionId'}
        if v in ({'Fn::GetAtt':['FrontendDistribution','DomainName']},{'Fn::GetAtt':'FrontendDistribution.DomainName'}):return {'Ref':'SharedDistributionDomain'}
        return {k:detach_visit(x) for k,x in v.items()}
    detached=deepcopy(protected)
    for n in names:del detached['Resources'][n]
    detached=detach_visit(detached)
    if 'HasUiContextOrigin' not in json.dumps(detached['Resources']):detached.get('Conditions',{}).pop('HasUiContextOrigin',None)
    detached['Parameters'].update(SharedDistributionId={'Type':'String'},SharedDistributionDomain={'Type':'String'})
    ids={'FrontendDistribution':frontend['distribution_id'],'OriginAccess':s3['oac_id']}
    # OriginRequestPolicy ID comes from the exact current stack resource inventory.
    ids['UiCountryOriginPolicy']=inventory.get('edge_resource_ids',{}).get('UiCountryOriginPolicy')
    imports=[{'ResourceType':r[n]['Type'],'LogicalResourceId':n,'ResourceIdentifier':{'Id':ids[n]}} for n in sorted(names)]
    return {'retain':protected,'detach':detached,'import':shared,'resources_to_import':imports,
        'import_parameters':{'OriginDomain':s3['domain'],'UiApiOriginDomain':next(o['domain'] for o in frontend['origins'] if o['id']=='ui-context-api')},
        'detach_parameters':{'SharedDistributionId':frontend['distribution_id'],'SharedDistributionDomain':frontend['distribution_domain']}}

def regional_shared(current,distribution_id,distribution_domain):
    """Fresh regional stacks reference the adopted edge; create no replacement CDN."""
    if not re.fullmatch(r'[A-Z0-9]+',distribution_id) or not re.fullmatch(r'[a-z0-9]+\.cloudfront\.net',distribution_domain):
        raise ValueError('Explicit existing CloudFront ID and domain required')
    # The same pure transformation is used for a detach and a fresh regional build.
    inventory={'frontend':{'distribution_id':distribution_id,'distribution_domain':distribution_domain,
        'origins':[{'id':'private-s3','domain':'unused.s3.ap-southeast-1.amazonaws.com','oac_id':'UNUSED'},
                   {'id':'ui-context-api','domain':'unused.execute-api.ap-southeast-1.amazonaws.com'}]}}
    result=split_edge(current,'unused',inventory)['detach']
    result['Parameters']['SharedDistributionId']['Default']=distribution_id
    result['Parameters']['SharedDistributionDomain']['Default']=distribution_domain
    result['Outputs']['FrontendOriginDomain']={'Value':{'Fn::GetAtt':['FrontendBucket','RegionalDomainName']}}
    return result

def redirect_code(primary,redirect):
    """CloudFront Functions JS 2.0, preserve every query value including duplicates."""
    return '''function handler(event) {
var r=event.request;
if(r.headers.host.value.toLowerCase().split(':')[0]!==REDIRECT)return r;
var q=[];Object.keys(r.querystring).forEach(function(k){var p=r.querystring[k];(p.multiValue||[p]).forEach(function(v){q.push(k+'='+v.value);});});
return {statusCode:308,statusDescription:'Permanent Redirect',headers:{location:{value:'https://'+PRIMARY+r.uri+(q.length?'?'+q.join('&'):'')},'cache-control':{value:'public,max-age=300'}}};
}'''.replace('REDIRECT',json.dumps(redirect)).replace('PRIMARY',json.dumps(primary))

def configure_edge(shared,c):
    result=deepcopy(shared);r=result['Resources'];p=result['Parameters'];d=r['FrontendDistribution']['Properties']['DistributionConfig']
    result.setdefault('Outputs',{}).update(DistributionId={'Value':{'Ref':'FrontendDistribution'}},
        DistributionDomain={'Value':{'Fn::GetAtt':['FrontendDistribution','DomainName']}})
    p['FrontendCertificateArn']={'Type':'String','Description':'Issued ACM certificate in us-east-1'}
    d['Aliases']=[c['FRONTEND_DOMAIN']]+([c['REDIRECT_DOMAIN']] if c.get('REDIRECT_DOMAIN') else [])
    d['ViewerCertificate']={'AcmCertificateArn':{'Ref':'FrontendCertificateArn'},'SslSupportMethod':'sni-only','MinimumProtocolVersion':'TLSv1.2_2021'}
    d['IPV6Enabled']=c['IPV6_ENABLED'];d['DefaultCacheBehavior']['ViewerProtocolPolicy']='redirect-to-https'
    p['UiApiOriginPath']={'Type':'String','Default':'','AllowedPattern':'(|/[A-Za-z0-9_-]+)','Description':'Raw API stage path; empty for $default, independent of public API mapping'}
    for origin in d['Origins']:
        body=origin['Fn::If'][1] if 'Fn::If' in origin else origin
        if body['Id']=='ui-context-api':body['OriginPath']={'Ref':'UiApiOriginPath'}
    # Current client uses hash routes. Never turn S3/API errors into index.html.
    if d.get('CustomErrorResponses'):raise ValueError('Review existing error responses before custom hosting')
    d['CacheBehaviors']=[b for b in d.get('CacheBehaviors',[]) if b.get('PathPattern') not in ('config.js','index.html')]
    for path in ('config.js','index.html'):
        b=deepcopy(d['DefaultCacheBehavior']);b.update(PathPattern=path,CachePolicyId=DISABLED_CACHE)
        d.setdefault('CacheBehaviors',[]).insert(0,b)
    # Nearby Asian edges, short edge TTL with compression for HTML/assets;
    # config.js stays uncached (see performance_infra).
    from performance_infra import tune_distribution,edge_api_cache
    tune_distribution(r,{'Fn::Sub':'${AWS::StackName}-frontend-edge'},'https://'+c['API_DOMAIN'])
    edge_api_cache(r)
    from edge_waf import attach
    attach(result)
    if c.get('REDIRECT_DOMAIN'):
        r['CanonicalRedirect']=retain({'Type':'AWS::CloudFront::Function','Properties':{'Name':{'Fn::Sub':'${AWS::StackName}-canonical'},'AutoPublish':True,
            'FunctionConfig':{'Comment':'Canonical hostname only; no error rewrite','Runtime':'cloudfront-js-2.0'},'FunctionCode':redirect_code(c['FRONTEND_DOMAIN'],c['REDIRECT_DOMAIN'])}})
        association={'EventType':'viewer-request','FunctionARN':{'Fn::GetAtt':['CanonicalRedirect','FunctionARN']}}
        prior=d['DefaultCacheBehavior'].get('FunctionAssociations',[])
        if prior and prior!=[association]:raise ValueError('Existing viewer function needs explicit composition')
        d['DefaultCacheBehavior']['FunctionAssociations']=[association]
        for b in d.get('CacheBehaviors',[]):
            body=b['Fn::If'][1] if 'Fn::If' in b else b
            if body.get('FunctionAssociations') and body['FunctionAssociations']!=[association]:raise ValueError('Existing viewer function needs explicit composition')
            body['FunctionAssociations']=[association]
    else:
        association={'EventType':'viewer-request','FunctionARN':{'Fn::GetAtt':['CanonicalRedirect','FunctionARN']}}
        for b in [d['DefaultCacheBehavior'],*d.get('CacheBehaviors',[])]:
            body=b['Fn::If'][1] if 'Fn::If' in b else b
            if body.get('FunctionAssociations')==[association]:body.pop('FunctionAssociations')
        # Keep the retained function tracked; disabling www only detaches it.
    return result
