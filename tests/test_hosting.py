from copy import deepcopy
import json,subprocess,sys,tempfile,unittest,hashlib,io,contextlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from generate_infra import build_template
from hosting import config,select_zone,covers,check_certificate,split_edge,configure_edge,api_template,dns_template,certificate_template,patch_regional,public_config,redirect_code,PROTECTED_TYPES
from prepare_hosting import prepare,api_domain_plan
from prepare_hosting_cutover import prepare as prepare_cutover,READINESS
from build_pages_live import public_config as validate_public,build
from hosting_changeset import validate_changes,dns_guard,certificate_guard,main as changeset_main
from unittest.mock import Mock,patch

def sample():
    c=json.loads((ROOT/'config/hosting.example.json').read_text())
    c.update(ACCOUNT_ID='123456789012',ROOT_DOMAIN='example.com',FRONTEND_DOMAIN='app.example.com',API_DOMAIN='api.example.com')
    return c

def inventory():
    return {'account_id':'123456789012','primary_region':'ap-southeast-1','stack_name':'cloudhub-source',
        'frontend':{'bucket':'example-private','distribution_id':'EEXAMPLE','distribution_domain':'example.cloudfront.net',
          'origins':[{'id':'private-s3','domain':'example-private.s3.ap-southeast-1.amazonaws.com','oac_id':'EOAC'},
                     {'id':'ui-context-api','domain':'api123.execute-api.ap-southeast-1.amazonaws.com'}]},
        'edge_resource_ids':{'UiCountryOriginPolicy':'00000000-0000-0000-0000-000000000000'},'hosted_zones':[],
        'api':{'id':'api123'},'cognito':{'region':'ap-southeast-1','client_id':'client123','hosted_domain':'https://cloudhub-example.auth.ap-southeast-1.amazoncognito.com'}}

class HostingTests(unittest.TestCase):
    def test_missing_domain_and_invalid_hostnames_fail_closed(self):
        for host in ('','https://example.com','example.com/path','bad..com','127.0.0.1','a\n.example.com','*.example.com','example.com:443'):
            with self.subTest(host=host),self.assertRaises(ValueError):config({**sample(),'FRONTEND_DOMAIN':host})
        with self.assertRaises(ValueError):config({**sample(),'API_DOMAIN':'example.com.evil.test'})
        with self.assertRaises(ValueError):config({**sample(),'API_DOMAIN':'app.example.com'})

    def test_explicit_public_zone_is_required_and_must_cover_hosts(self):
        c=config({**sample(),'DNS_PROVIDER':'route53','ROUTE53_HOSTED_ZONE_ID':'ZRIGHT'})
        zones=[{'id':'ZRIGHT','name':'example.com.','private':False},{'id':'ZOTHER','name':'example.com.','private':False}]
        self.assertEqual(select_zone(zones,c)['id'],'ZRIGHT')
        for rows in ([{**zones[0],'private':True}],[],[{**zones[0],'name':'evil-example.com.'}],zones+[zones[0]]):
            with self.assertRaises(ValueError):select_zone(rows,c)

    def test_cert_region_account_and_wildcard_coverage(self):
        c=config(sample());arn='arn:aws:acm:us-east-1:123456789012:certificate/1234'
        detail={'CertificateArn':arn,'DomainName':'*.example.com','SubjectAlternativeNames':['*.example.com'],'Status':'ISSUED'}
        self.assertEqual(check_certificate(detail,c,True),arn)
        self.assertFalse(covers('*.example.com','example.com'));self.assertFalse(covers('*.example.com','a.b.example.com'))
        for d in ({**detail,'Status':'PENDING_VALIDATION'},{**detail,'CertificateArn':arn.replace('us-east-1','ap-southeast-1')},
                  {**detail,'SubjectAlternativeNames':['wrong.example.com']}):
            with self.assertRaises(ValueError):check_certificate(d,c,True)

    def test_split_keeps_ids_oac_and_properties_without_copying_secrets(self):
        original=build_template();before=deepcopy(original);s=split_edge(original,'cloudhub-source',inventory())
        self.assertEqual(original,before)
        self.assertEqual(len(s['resources_to_import']),3)
        self.assertEqual(next(x for x in s['resources_to_import'] if x['LogicalResourceId']=='FrontendDistribution')['ResourceIdentifier'],{'Id':'EEXAMPLE'})
        self.assertNotIn('FrontendDistribution',s['detach']['Resources'])
        self.assertEqual(s['import']['Parameters']['UiEdgeSecret']['NoEcho'],True)
        self.assertNotIn('Default',s['import']['Parameters']['UiEdgeSecret'])
        self.assertNotIn('FrontendBucket',json.dumps(s['import']))
        dist=s['import']['Resources']['FrontendDistribution']['Properties']['DistributionConfig']
        self.assertEqual(dist['ViewerCertificate'],{'CloudFrontDefaultCertificate':True})
        self.assertEqual(dist['Origins'][0]['OriginAccessControlId'],{'Ref':'OriginAccess'})
        self.assertIn('cloudhub-source-oac',json.dumps(s['import']))
        for name in ('ApiFunction','WorkerFunction','UserPool','UserClient','HttpApi'):
            # Only reference expressions to the same shared distribution change.
            self.assertEqual(s['retain']['Resources'][name]['Properties'],original['Resources'][name]['Properties'])

    def test_regional_stack_creation_uses_existing_edge_without_new_cdn(self):
        t=build_template(shared_edge={'id':'EEXAMPLE','domain':'example.cloudfront.net'})
        self.assertFalse(any(r['Type'].startswith('AWS::CloudFront::') for r in t['Resources'].values()))
        self.assertIn('FrontendBucket',t['Resources'])
        p=json.dumps(t['Resources']['FrontendBucketPolicy']);self.assertIn('${SharedDistributionId}',p)
        self.assertNotIn('${FrontendDistribution',json.dumps(t))
        for r in t['Resources'].values():
            if r['Type'] in PROTECTED_TYPES:self.assertEqual(r['DeletionPolicy'],'Retain')

    def test_edge_https_cache_and_country_route_are_safe_and_idempotent(self):
        s=split_edge(build_template(),'cloudhub-source',inventory())['import'];c=config(sample())
        e=configure_edge(s,c);self.assertEqual(configure_edge(e,c),e)
        d=e['Resources']['FrontendDistribution']['Properties']['DistributionConfig']
        self.assertEqual(d['Aliases'],['app.example.com']);self.assertEqual(d['ViewerCertificate']['MinimumProtocolVersion'],'TLSv1.2_2021')
        self.assertFalse(d.get('CustomErrorResponses'));self.assertEqual(d['Origins'][0]['S3OriginConfig']['OriginAccessIdentity'],'')
        for path in ('config.js','index.html'):
            b=next(x for x in d['CacheBehaviors'] if x.get('PathPattern')==path)
            self.assertEqual(b['CachePolicyId'],'4135ea2d-6df8-44a3-9df3-4b5a84be39ad')
        country=next(b['Fn::If'][1] for b in d['CacheBehaviors'] if 'Fn::If' in b)
        self.assertEqual(country['PathPattern'],'/ui-context');self.assertEqual(country['AllowedMethods'],['GET','HEAD'])

    def test_custom_urls_preserve_cognito_auth_code_and_owner_backend(self):
        original=build_template();r=patch_regional(original,config(sample()))['Resources']
        self.assertEqual(r['HttpApi']['Properties']['Auth'],original['Resources']['HttpApi']['Properties']['Auth'])
        for key in ('ExplicitAuthFlows','AllowedOAuthFlows','AllowedOAuthScopes','GenerateSecret','UserPoolId'):
            self.assertEqual(r['UserClient']['Properties'][key],original['Resources']['UserClient']['Properties'][key])
        for name in ('ApiFunction','WorkerFunction','SweepFunction','ExpiryFunction'):
            self.assertEqual(r[name]['Properties']['CodeUri'],original['Resources'][name]['Properties']['CodeUri'])
        self.assertIn('https://app.example.com',r['HttpApi']['Properties']['CorsConfiguration']['AllowOrigins'])
        self.assertIn('https://app.example.com/',r['UserClient']['Properties']['CallbackURLs'])

    def test_region_change_keeps_urls_and_identity_and_changes_only_api_dns_target_input(self):
        a=config({**sample(),'DNS_PROVIDER':'route53','ROUTE53_HOSTED_ZONE_ID':'ZEXAMPLE'})
        b=config({**a,'PRIMARY_REGION':'us-east-1'})
        self.assertEqual(a['frontend_url'],b['frontend_url']);self.assertEqual(a['api_url'],b['api_url'])
        self.assertEqual(public_config(a,inventory()),public_config(b,inventory()))
        da=dns_template(a,'example.cloudfront.net');db=dns_template(b,'example.cloudfront.net');self.assertEqual(da,db)
        self.assertFalse(any('HostedZone'==v['Type'].split('::')[-1] for v in da['Resources'].values()))
        self.assertEqual({x['Properties']['Type'] for x in da['Resources'].values()},{'A','AAAA'})
        self.assertTrue(all(x['DeletionPolicy']=='Retain' for x in da['Resources'].values()))

    def test_public_config_requires_central_approval_of_custom_api_and_no_private_fields(self):
        raw=sample();value=public_config(config(raw),inventory())
        self.assertEqual(validate_public(value,raw),value)
        for bad in ({**value,'apiBase':'https://attacker.example.com'},{**value,'apiBase':value['apiBase']+'?token=x'},
                    {**value,'region':'us-east-1'},{**value,'secret':'bad'}):
            with self.assertRaises(ValueError):validate_public(bad,raw)
        with tempfile.TemporaryDirectory() as p:
            build(p,value,raw);self.assertIn('https://api.example.com',(Path(p)/'config.js').read_text())

    def test_api_mapping_and_external_certificate_have_no_dns_side_effects(self):
        c=config(sample());t=api_template(c,'api123')
        self.assertEqual(t['Resources']['ApiMapping']['Properties']['Stage'],'$default')
        self.assertEqual(t['Resources']['ApiDomain']['Properties']['DomainNameConfigurations'][0]['SecurityPolicy'],'TLS_1_2')
        self.assertFalse(any(r['Type'].startswith('AWS::Route53::') for r in t['Resources'].values()))
        cert=certificate_template(['app.example.com']);self.assertNotIn('DomainValidationOptions',cert['Resources']['Certificate']['Properties'])
        cert=certificate_template(['example.com','www.example.com'],'ZEXAMPLE')
        self.assertEqual(len(cert['Resources']['Certificate']['Properties']['DomainValidationOptions']),2)
        self.assertEqual(cert['Resources']['Certificate']['Properties']['CertificateExport'],'DISABLED')

    def test_new_public_zone_is_retained_without_registrar_or_mail_mutations(self):
        from hosting import hosted_zone_template
        t=hosted_zone_template('example.com')
        self.assertEqual(set(t['Resources']),{'PublicZone'})
        z=t['Resources']['PublicZone']
        self.assertEqual(z['DeletionPolicy'],'Retain')
        self.assertEqual(z['UpdateReplacePolicy'],'Retain')
        self.assertNotIn('VPCs',z['Properties'])
        self.assertEqual(z['Properties']['Name'],'example.com')

    def test_import_has_no_outputs_until_separate_edge_update(self):
        t=split_edge(build_template(),'cloudhub-source',inventory())['import']
        self.assertNotIn('Outputs',t)
        self.assertIn('DistributionId',configure_edge(t,config(sample()))['Outputs'])

    def test_redirect_executes_without_losing_percent_encoded_values_or_duplicate_queries(self):
        code=redirect_code('example.com','www.example.com')
        request={'uri':'/docs/a%2Fb','headers':{'host':{'value':'www.example.com'}},'querystring':{'q':{'value':'a%2Bb%20c'},'tag':{'value':'one','multiValue':[{'value':'one'},{'value':'two'}]}}}
        script="const fs=require('node:fs'),vm=require('node:vm');const x=JSON.parse(fs.readFileSync(0,'utf8'));console.log(JSON.stringify(vm.runInNewContext(x.code+';handler(input)',{input:{request:x.request}})));"
        result=subprocess.run(['node','-e',script],input=json.dumps({'code':code,'request':request}),capture_output=True,text=True,check=True)
        self.assertEqual(json.loads(result.stdout)['headers']['location']['value'],'https://example.com/docs/a%2Fb?q=a%2Bb%20c&tag=one&tag=two')
        c=config({**sample(),'FRONTEND_DOMAIN':'example.com','REDIRECT_DOMAIN':'www.example.com'})
        edge=configure_edge(split_edge(build_template(),'cloudhub-source',inventory())['import'],c)
        self.assertEqual(configure_edge(edge,c),edge)

    def test_missing_domain_still_prepares_safe_exact_split_and_marks_blocked(self):
        raw={**sample(),'ROOT_DOMAIN':'','FRONTEND_DOMAIN':'','API_DOMAIN':''}
        with tempfile.TemporaryDirectory() as p:
            review=prepare(raw,inventory(),build_template(),p)
            self.assertEqual(review['aws_mutations'],0);self.assertTrue(review['blockers'])
            self.assertTrue((Path(p)/'02-import-edge.json').is_file());self.assertFalse((Path(p)/'05-api-domain.json').exists())
        with tempfile.TemporaryDirectory() as p:
            review=prepare(sample(),inventory(),build_template(),p)
            self.assertTrue((Path(p)/'05-api-domain.json').is_file());self.assertIsNone(json.loads((Path(p)/'external-dns-records.json').read_text())[-1]['value'])

    def test_changeset_rejects_identity_replacement_new_distribution_and_iam(self):
        for name,typ,action,replacement in [('UserPool','AWS::Cognito::UserPool','Modify','True'),('FrontendDistribution','AWS::CloudFront::Distribution','Add','False'),
                ('MemberDistribution','AWS::CloudFront::Distribution','Remove','False'),('Table','AWS::DynamoDB::Table','Remove','False'),('SomeRole','AWS::IAM::Role','Modify','False')]:
            d={'Status':'CREATE_COMPLETE','ExecutionStatus':'AVAILABLE','Changes':[{'ResourceChange':{'LogicalResourceId':name,'ResourceType':typ,'Action':action,'Replacement':replacement}}]}
            with self.subTest(name=name),self.assertRaises(ValueError):validate_changes(d,{},'UPDATE')
        d={'Status':'CREATE_COMPLETE','ExecutionStatus':'AVAILABLE','Changes':[{'ResourceChange':{'LogicalResourceId':'FrontendDistribution','ResourceType':'AWS::CloudFront::Distribution','Action':'Import'}}]}
        self.assertTrue(validate_changes(d,{},'IMPORT'))

    def test_dns_guard_rejects_mx_and_foreign_records_before_any_aws_call(self):
        c=config({**sample(),'DNS_PROVIDER':'route53','ROUTE53_HOSTED_ZONE_ID':'ZEXAMPLE'});t=dns_template(c,'example.cloudfront.net');session=Mock()
        t['Resources']['ApiA']['Properties']['Type']='MX'
        with self.assertRaises(ValueError):dns_guard(session,t,{'allowed_dns_names':['api.example.com','app.example.com'],'hosted_zone_id':'ZEXAMPLE'})
        session.client.assert_not_called()

    def test_dynamic_iam_dependency_requires_identical_native_resource(self):
        t={'Resources':{'Role':{'Type':'AWS::IAM::Role','Properties':{'Policies':[]}}}}
        r={'Action':'Modify','LogicalResourceId':'Role','ResourceType':'AWS::IAM::Role','Replacement':'False',
           'Details':[{'Evaluation':'Dynamic','ChangeSource':'ResourceAttribute'}]}
        d={'Status':'CREATE_COMPLETE','ExecutionStatus':'AVAILABLE','Changes':[{'ResourceChange':r}]}
        self.assertTrue(validate_changes(d,t,'UPDATE',deepcopy(t)))
        for before in (None,{'Resources':{'Role':{'Type':'AWS::IAM::Role','Properties':{'Policies':['different']}}}}):
            with self.assertRaises(ValueError):validate_changes(d,t,'UPDATE',before)
        r['Details'][0]['Evaluation']='Static'
        with self.assertRaises(ValueError):validate_changes(d,t,'UPDATE',deepcopy(t))

    def test_certificate_wait_uses_requested_region_with_injected_session(self):
        with tempfile.TemporaryDirectory() as folder:
            review=Path(folder)/'review.json'
            review.write_text(json.dumps({'account_id':'123456789012','primary_region':'ap-southeast-1','shared_stack_region':'ap-southeast-1'}))
            session=Mock();sts=Mock();cf=Mock();acm=Mock()
            session.client.side_effect=lambda name,**kw:{'sts':sts,'cloudformation':cf,'acm':acm}[name]
            sts.get_caller_identity.return_value={'Account':'123456789012'}
            argv=['hosting_changeset.py','wait-certificate','--review',str(review),'--region','us-east-1',
                '--resource-id','arn:aws:acm:us-east-1:123456789012:certificate/front']
            with patch.object(sys,'argv',argv):changeset_main(session)
            session.client.assert_any_call('acm',region_name='us-east-1')
            acm.get_waiter.assert_called_once_with('certificate_validated')

    def test_repeated_prepare_after_adoption_does_not_import_or_recreate_distribution(self):
        source=build_template();s=split_edge(source,'cloudhub-source',inventory())
        with tempfile.TemporaryDirectory() as p:
            result=prepare(sample(),inventory(),s['detach'],p,s['import'])
            self.assertNotIn('02-import-edge.json',result['sha256']);self.assertNotIn('resources-to-import.json',result['sha256'])

    def test_existing_api_domain_is_reused_and_conflicting_mapping_is_not_overwritten(self):
        i=inventory();c=config(sample())
        domain={'domain':c['API_DOMAIN'],'status':'AVAILABLE','security_policy':'TLS_1_2','target':'native-api.example.amazonaws.com','target_zone':'ZAPI',
                'mappings':[{'ApiId':i['api']['id'],'Stage':'$default','ApiMappingKey':''}]}
        i['api']['custom_domain']=domain
        self.assertIsNone(api_domain_plan(c,i))
        for changes in ({'status':'UPDATING'},{'domain':'other.example.com'},{'mappings':[{'ApiId':'foreign','Stage':'$default'}]}):
            with self.assertRaises(ValueError):api_domain_plan(c,{**i,'api':{**i['api'],'custom_domain':{**domain,**changes}}})
        with tempfile.TemporaryDirectory() as p:
            r=prepare(sample(),i,build_template(),p)
            self.assertNotIn('05-api-domain.json',r['sha256']);self.assertIn('existing-api-domain.json',r['sha256'])

    def test_cutover_requires_new_origin_same_identity_and_readiness(self):
        c={**sample(),'PRIMARY_REGION':'us-east-1','API_STAGE':'demo','ADDITIONAL_MONTHLY_BUDGET_USD':1,'DNS_CHANGE_APPROVED':True,
           'API_CERTIFICATE_ARN':'arn:aws:acm:us-east-1:123456789012:certificate/api'}
        source=inventory();source['frontend']['aliases']=['app.example.com'];source['cognito']['pool_id']='existing-pool'
        target=deepcopy(source);target['primary_region']='us-east-1';target['target_frontend_origin']='target.s3.us-east-1.amazonaws.com'
        target['api']={'id':'target-api','endpoint':'https://target-api.execute-api.us-east-1.amazonaws.com','custom_domain':{'domain':'api.example.com','status':'AVAILABLE','security_policy':'TLS_1_2',
            'target':'target-native.execute-api.us-east-1.amazonaws.com','target_zone':'ZTARGET','mappings':[{'ApiId':'target-api','Stage':'demo','ApiMappingKey':''}]}}
        edge=split_edge(build_template(),'cloudhub-source',source)['import']
        with tempfile.TemporaryDirectory() as p:
            r=prepare_cutover(c,source,target,edge,{k:True for k in READINESS},p)
            self.assertEqual(r['blockers'],[]);self.assertEqual(r['customer_environments_moved'],0);self.assertFalse(r['retire_source_allowed'])
            params=json.loads((Path(p)/'edge-parameters.json').read_text());self.assertEqual(params['UiApiOriginPath'],'/demo')
            self.assertEqual(params['OriginDomain'],target['target_frontend_origin'])
            self.assertNotIn('target-api-domain.json',r['sha256'])
            self.assertEqual(json.loads((Path(p)/'frontend-public.json').read_text())['region'],'ap-southeast-1')
        with tempfile.TemporaryDirectory() as p:
            r=prepare_cutover(c,source,target,edge,{},p);self.assertEqual(set(r['blockers']),set(READINESS))
        for changed in ({'target_frontend_origin':'old.s3.ap-southeast-1.amazonaws.com'},
                        {'cognito':{**target['cognito'],'pool_id':'different-pool'}},
                        {'frontend':{**target['frontend'],'distribution_id':'ENEW'}}):
            with tempfile.TemporaryDirectory() as p,self.assertRaises(ValueError):prepare_cutover(c,source,{**target,**changed},edge,{},p)

    def test_stale_review_files_are_not_silently_mixed_into_new_plan(self):
        with tempfile.TemporaryDirectory() as p:
            (Path(p)/'unrelated.json').write_text('{}')
            with self.assertRaises(ValueError):prepare(sample(),inventory(),build_template(),p)

    def test_disabling_www_detaches_only_our_function_and_keeps_country_route(self):
        edge=split_edge(build_template(),'cloudhub-source',inventory())['import']
        enabled=configure_edge(edge,config({**sample(),'REDIRECT_DOMAIN':'www.example.com'}))
        disabled=configure_edge(enabled,config(sample()))
        self.assertIn('CanonicalRedirect',disabled['Resources'])
        d=disabled['Resources']['FrontendDistribution']['Properties']['DistributionConfig']
        self.assertNotIn('FunctionAssociations',d['DefaultCacheBehavior'])
        country=next(b['Fn::If'][1] for b in d['CacheBehaviors'] if 'Fn::If' in b)
        self.assertNotIn('FunctionAssociations',country)
        self.assertEqual(d['Origins'][1]['Fn::If'][1]['OriginPath'],{'Ref':'UiApiOriginPath'})

    def test_legacy_unconditional_country_origin_is_adopted_without_invented_conditions(self):
        source=build_template();source['Parameters'].pop('UiApiOriginDomain');source['Conditions'].pop('HasUiContextOrigin')
        d=source['Resources']['FrontendDistribution']['Properties']['DistributionConfig']
        d['Origins'][1]=d['Origins'][1]['Fn::If'][1];d['Origins'][1]['DomainName']='api123.execute-api.ap-southeast-1.amazonaws.com'
        d['CacheBehaviors']=[x['Fn::If'][1] if 'Fn::If' in x else x for x in d['CacheBehaviors']]
        s=split_edge(source,'cloudhub-source',inventory())
        self.assertNotIn('Conditions',s['import']);self.assertNotIn('Default',s['import']['Parameters']['UiApiOriginDomain'])
        self.assertEqual(s['import_parameters']['UiApiOriginDomain'],d['Origins'][1]['DomainName'])
        self.assertEqual(configure_edge(s['import'],config(sample()))['Resources']['FrontendDistribution']['Properties']['DistributionConfig']['Origins'][1]['OriginPath'],{'Ref':'UiApiOriginPath'})

    def test_certificate_is_checked_before_native_changeset_creation(self):
        session=Mock();arn='arn:aws:acm:ap-southeast-1:123456789012:certificate/api'
        session.client.return_value.describe_certificate.return_value={'Certificate':{'Status':'ISSUED','DomainName':'api.example.com','SubjectAlternativeNames':['api.example.com']}}
        t=api_template(config(sample()),'api123')
        certificate_guard(session,t,{'CertificateArn':arn},{},'123456789012','ap-southeast-1')
        session.client.assert_called_with('acm',region_name='ap-southeast-1')
        for value in ('arn:aws:acm:us-east-1:123456789012:certificate/api','arn:aws:acm:ap-southeast-1:999999999999:certificate/api'):
            with self.assertRaises(ValueError):certificate_guard(session,t,{'CertificateArn':value},{},'123456789012','ap-southeast-1')
        session.client.return_value.describe_certificate.return_value['Certificate']['Status']='PENDING_VALIDATION'
        with self.assertRaises(ValueError):certificate_guard(session,t,{}, {'CertificateArn':{'ParameterValue':arn}},'123456789012','ap-southeast-1')

    def test_retry_of_completed_native_changeset_does_not_execute_it_again(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);t=p/'api.json';r=p/'review.json';m=p/'manifest.json'
            t.write_text(json.dumps(api_template(config(sample()),'api123')),encoding='utf-8')
            sha=lambda f:hashlib.sha256(f.read_bytes()).hexdigest()
            r.write_text(json.dumps({'account_id':'123456789012','primary_region':'ap-southeast-1','shared_stack_region':'ap-southeast-1','sha256':{'api.json':sha(t)}}),encoding='utf-8')
            m.write_text(json.dumps({'review_sha256':sha(r),'template_sha256':sha(t),'region':'ap-southeast-1','change_set_id':'change123','stack_id':'stack123','kind':'CREATE'}),encoding='utf-8')
            cf=Mock();sts=Mock();session=Mock();session.client.side_effect=lambda s,**kw:{'cloudformation':cf,'sts':sts}[s]
            sts.get_caller_identity.return_value={'Account':'123456789012'}
            cf.describe_change_set.return_value={'Status':'CREATE_COMPLETE','ExecutionStatus':'EXECUTE_COMPLETE','Description':'CloudHub hosting reviewed '+sha(r),'StackId':'stack123'}
            args=['hosting_changeset.py','execute','--review',str(r),'--template',str(t),'--manifest',str(m),'--region','ap-southeast-1','--approved']
            with patch.object(sys,'argv',args),patch('boto3.Session',return_value=session),contextlib.redirect_stdout(io.StringIO()) as output:changeset_main()
            self.assertIn('ALREADY_EXECUTED',output.getvalue());cf.execute_change_set.assert_not_called();cf.update_termination_protection.assert_not_called()

    def test_dns_change_requires_recorded_approval_before_looking_up_zone(self):
        c=config({**sample(),'DNS_PROVIDER':'route53','ROUTE53_HOSTED_ZONE_ID':'ZEXAMPLE'});session=Mock()
        with self.assertRaises(ValueError):dns_guard(session,dns_template(c,'example.cloudfront.net'),{'allowed_dns_names':['api.example.com','app.example.com'],'hosted_zone_id':'ZEXAMPLE','dns_change_approved':False})
        session.client.assert_not_called()

    def test_native_openapi_cors_layout_keeps_paths_integrations_and_security(self):
        t=build_template();a=t['Resources']['HttpApi'];sam=a['Properties']
        a['Type']='AWS::ApiGatewayV2::Api';a['Properties']={'Body':{'openapi':'3.0.1','paths':{'/private':{'get':{'security':[{'jwt':['cloudhub/use']}],'x-amazon-apigateway-integration':{'type':'aws_proxy'}}}},
            'components':{'securitySchemes':{'jwt':{'type':'oauth2'}}},'x-amazon-apigateway-cors':{'allowOrigins':sam['CorsConfiguration']['AllowOrigins'],'allowMethods':['GET','POST','PUT','OPTIONS']}}}
        before=deepcopy(a['Properties']['Body']);after=patch_regional(t,config(sample()))['Resources']['HttpApi']['Properties']['Body']
        self.assertEqual(after['paths'],before['paths']);self.assertEqual(after['components'],before['components'])
        self.assertEqual(after['x-amazon-apigateway-cors']['allowMethods'],before['x-amazon-apigateway-cors']['allowMethods'])
        self.assertIn('https://app.example.com',after['x-amazon-apigateway-cors']['allowOrigins'])

if __name__=='__main__':unittest.main()
