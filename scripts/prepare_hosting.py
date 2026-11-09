"""Prepare concrete CloudFormation files and a review; never write AWS or DNS."""
import argparse,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
from hosting import config,split_edge,configure_edge,patch_regional,certificate_template,api_template,dns_template,external_records,public_config,select_zone

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def review_directory(destination):
    out=Path(destination).resolve();project=Path(__file__).resolve().parents[1]
    if out==project or out.is_relative_to(project) or project.is_relative_to(out):raise ValueError('Use a dedicated private review directory outside the source repository')
    return out

def api_domain_plan(c,inventory):
    """Reuse a working existing domain; never create or overwrite a conflicting one."""
    domain=inventory['api'].get('custom_domain')
    if domain:
        good=domain.get('domain')==c['API_DOMAIN'] and domain.get('status')=='AVAILABLE' and domain.get('security_policy')=='TLS_1_2' and any(
            m['ApiId']==inventory['api']['id'] and m['Stage']==c['API_STAGE'] and m.get('ApiMappingKey','')==c['API_MAPPING_KEY'] for m in domain.get('mappings',[]))
        if not good:raise ValueError('Existing API custom domain needs review by its current owner; no duplicate or mapping overwrite prepared')
        return None
    return api_template(c,inventory['api']['id'])

def prepare(raw,inventory,current,destination,shared_template=None):
    out=review_directory(destination)
    if raw['ACCOUNT_ID']!=inventory['account_id'] or raw['PRIMARY_REGION']!=inventory['primary_region']:raise ValueError('Inventory account/Region mismatch')
    if shared_template is not None and 'FrontendDistribution' not in current['Resources']:
        from hosting import PROTECTED_TYPES,retain
        retained=json.loads(json.dumps(current))
        for r in retained['Resources'].values():
            if r['Type'] in PROTECTED_TYPES:retain(r)
        split={'retain':retained,'detach':retained,'import':shared_template,'resources_to_import':[],
            'detach_parameters':{},'import_parameters':{}}
    else:
        if raw['SHARED_STACK_REGION']!=inventory.get('edge_stack_region',inventory['primary_region']):raise ValueError('Adopt the edge in its source stack Region; do not move global ownership implicitly')
        split=split_edge(current,inventory['stack_name'],inventory)
    if any(not x['ResourceIdentifier']['Id'] for x in split['resources_to_import']):raise ValueError('Inventory requires exact edge resource IDs')
    generated={'00-retain.json':split['retain']}
    if split['resources_to_import']:
        generated.update({'01-detach-edge.json':split['detach'],'02-import-edge.json':split['import'],
            'resources-to-import.json':split['resources_to_import'],'detach-parameters.json':split['detach_parameters'],'import-public-parameters.json':split['import_parameters']})
    blockers=[]
    try:c=config(raw)
    except ValueError as exc:blockers.append(str(exc));c=None
    if c:
        if c['DNS_PROVIDER']=='route53':select_zone(inventory['hosted_zones'],c)
        generated['03-configure-edge.json']=configure_edge(split['import'],c)
        generated['04-regional-auth-urls.json']=patch_regional(split['detach'],c)
        api_plan=api_domain_plan(c,inventory)
        if api_plan:generated['05-api-domain.json']=api_plan
        else:generated['existing-api-domain.json']=inventory['api']['custom_domain']
        generated['edge-domain-parameters.json']={'UiApiOriginPath':'' if c['API_STAGE']=='$default' else '/'+c['API_STAGE']}
        if c.get('FRONTEND_CERTIFICATE_ARN'):generated['edge-domain-parameters.json']['FrontendCertificateArn']=c['FRONTEND_CERTIFICATE_ARN']
        if c.get('API_CERTIFICATE_ARN'):generated['api-domain-parameters.json']={'CertificateArn':c['API_CERTIFICATE_ARN']}
        names=[c['FRONTEND_DOMAIN']]+([c['REDIRECT_DOMAIN']] if c.get('REDIRECT_DOMAIN') else [])
        zone=c['ROUTE53_HOSTED_ZONE_ID'] if c['DNS_PROVIDER']=='route53' else ''
        if not c.get('FRONTEND_CERTIFICATE_ARN'):generated['certificate-frontend-us-east-1.json']=certificate_template(names,zone)
        if not c.get('API_CERTIFICATE_ARN'):generated['certificate-api-'+c['PRIMARY_REGION']+'.json']=certificate_template([c['API_DOMAIN']],zone)
        routing=dns_template(c,inventory['frontend']['distribution_domain'])
        if routing:generated['06-shared-routing.json']=routing
        existing=inventory['api'].get('custom_domain')
        if existing:generated['routing-parameters.json']={'ApiTargetDomain':existing['target'],'ApiTargetZone':existing['target_zone']}
        generated['external-dns-records.json']=external_records(c,inventory['frontend']['distribution_domain'],(inventory['api'].get('custom_domain') or {}).get('target'))
        generated['frontend-public.json']=public_config(c,inventory)
        if not c.get('FRONTEND_CERTIFICATE_ARN'):blockers.append('Frontend ACM certificate not yet issued/selected in us-east-1')
        if not c.get('API_CERTIFICATE_ARN'):blockers.append('API ACM certificate not yet issued/selected in PRIMARY_REGION')
        blockers.append('Public DNS delegation and alias ownership must be verified before DNS change')
    if not raw.get('DNS_CHANGE_APPROVED'):blockers.append('Production DNS change has not been approved')
    if not raw.get('ADDITIONAL_MONTHLY_BUDGET_USD'):blockers.append('Additional hosting/DNS budget not yet reviewed')
    if out.exists():
        stale=[p.name for p in out.iterdir() if p.is_file() and p.name not in {*generated,'review.json'}]
        if stale:raise ValueError('Use a fresh review directory; stale or unreviewed files: '+', '.join(stale))
    hashes={}
    for name,value in generated.items():write(out/name,value);hashes[name]=hashlib.sha256((out/name).read_bytes()).hexdigest()
    review={'recorded_at':datetime.now(timezone.utc).isoformat(),'mode':'PREPARED_NOT_DEPLOYED','account_id':raw['ACCOUNT_ID'],
        'primary_region':raw['PRIMARY_REGION'],'shared_stack_region':raw['SHARED_STACK_REGION'],'domain':c['ROOT_DOMAIN'] if c else None,
        'existing_distribution_id':inventory['frontend']['distribution_id'],
        'allowed_dns_names':[c['FRONTEND_DOMAIN'],c['API_DOMAIN']]+([c['REDIRECT_DOMAIN']] if c.get('REDIRECT_DOMAIN') else []) if c else [],
        'hosted_zone_id':c['ROUTE53_HOSTED_ZONE_ID'] if c else None,
        'dns_change_approved':raw.get('DNS_CHANGE_APPROVED') is True,
        'blockers':blockers,'aws_mutations':0,'resource_plan':[
            'Reuse existing public hosted zone; never create/register a domain automatically.',
            'Retain/detach/import the exact existing CloudFront distribution, OAC and country policy in the source stack Region.',
            'Reuse issued certificates or provision DNS-validated retained certificates: frontend us-east-1, API PRIMARY_REGION.',
            'Regional HTTP API custom domain and root/base-path API mapping; API/stage/JWT remain existing.',
            'Shared routing stack owns only configured frontend/www/API A/AAAA records; old regional stack owns no routing records.'],
        'cost_review':{'approved_additional_monthly_usd':raw.get('ADDITIONAL_MONTHLY_BUDGET_USD',0),'domain_registration_usd':None,
            'route53_hosted_zone_newly_created':False,'reuse_distribution':True,'no_extra_workload':True,
            'note':'Registration/renewal depends on registrar/TLD. Route53 zone, queries, CloudFront traffic/functions and logs may cost; confirm current rates/credits. No invoice cap is implied.'},
        'rollback':'Keep source endpoints/origins/certificates. Before reversal fence writes/jobs and reconcile new data and operations; reversing DNS alone is insufficient.',
        'cleanup':'Remove old regional resources only after data/identity/workload retention review; keep shared edge/routing, validation CNAMEs, certificates and retained data.',
        'next_step':'Read docs/custom-domain.md; review each native changeset. No automatic execution.', 'sha256':hashes}
    write(out/'review.json',review);return review

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--inventory',type=Path);p.add_argument('--template',type=Path);p.add_argument('--edge-template',type=Path);p.add_argument('--inspect-stack');p.add_argument('--profile')
    p.add_argument('--validation-certificate');args=p.parse_args();raw=json.loads(args.config.read_text(encoding='utf-8'))
    review_directory(args.out)
    if args.validation_certificate:
        import boto3
        from hosting_aws import validation_records
        arn=args.validation_certificate;region=arn.split(':')[3]
        if arn.split(':')[4]!=raw['ACCOUNT_ID']:p.error('Certificate account mismatch')
        value=validation_records(boto3.Session(profile_name=args.profile).client('acm',region_name=region),arn)
        write(args.out/'validation-records.json',value);print(json.dumps(value));return
    if args.inspect_stack:
        import boto3
        from hosting_aws import inspect
        session=boto3.Session(profile_name=args.profile)
        inventory,source=inspect(session,raw,args.inspect_stack)
        write(args.out/'inventory.json',inventory);write(args.out/'original-template.private.json',source)
        if raw.get('SHARED_EDGE_STACK_NAME'):
            shared=session.client('cloudformation',region_name=raw['SHARED_STACK_REGION']).get_template(StackName=raw['SHARED_EDGE_STACK_NAME'],TemplateStage='Original')['TemplateBody']
            write(args.out/'shared-edge-template.private.json',json.loads(shared) if isinstance(shared,str) else shared)
        print(json.dumps({'mode':'AWS_READ_ONLY','output':str(args.out),'domain_changes_made':False}));return
    if not args.inventory or not args.template:p.error('--inventory and --template are required to prepare')
    review=prepare(raw,json.loads(args.inventory.read_text(encoding='utf-8')),json.loads(args.template.read_text(encoding='utf-8')),args.out,
        json.loads(args.edge_template.read_text(encoding='utf-8')) if args.edge_template else None)
    print(json.dumps({'mode':review['mode'],'blockers':review['blockers'],'files':len(review['sha256'])}))

if __name__=='__main__':main()
