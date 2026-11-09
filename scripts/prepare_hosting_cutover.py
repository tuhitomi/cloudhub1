"""Prepare target parameters; never migrate data, identities, workloads or DNS."""
import argparse,json,hashlib
from pathlib import Path
from hosting import config,public_config,dns_template,configure_edge,external_records
from prepare_hosting import write,review_directory,api_domain_plan

READINESS=('data_migration_verified','identity_verified','inflight_operations_reconciled','target_health_verified','rollback_data_plan_reviewed')

def prepare(raw,source,target,edge,evidence,out):
    c=config(raw)
    if source['account_id']!=c['ACCOUNT_ID'] or target['account_id']!=c['ACCOUNT_ID'] or target['primary_region']!=c['PRIMARY_REGION']:
        raise ValueError('Target account or Region mismatch')
    if source['frontend']['distribution_id']!=target['frontend']['distribution_id']:raise ValueError('Region cutover must keep the same distribution ID')
    if source['cognito']['client_id']!=target['cognito']['client_id'] or source['cognito']['pool_id']!=target['cognito']['pool_id']:
        raise ValueError('Identity migration requires a separate reviewed plan; no implicit account replacement')
    aliases=source['frontend'].get('aliases',[])
    if c['FRONTEND_DOMAIN'] not in aliases:raise ValueError('Public frontend domain must already be attached to the retained distribution before cutover')
    if source.get('edge_stack_region',c['SHARED_STACK_REGION'])!=c['SHARED_STACK_REGION']:raise ValueError('Keep shared edge ownership in its existing Region')
    # Target inventory is collected against the existing edge, so the new regional
    # origin must be an explicit successful target-stack output, not old CF origin.
    origin=target.get('target_frontend_origin')
    if not origin or not origin.endswith('.s3.'+c['PRIMARY_REGION']+'.amazonaws.com'):raise ValueError('Explicit target regional S3 REST output required')
    api_host=target['api']['endpoint'].removeprefix('https://')
    blockers=[k for k in READINESS if evidence.get(k) is not True]
    if not c.get('API_CERTIFICATE_ARN'):blockers.append('Issued API certificate in target Region required')
    domain=target['api'].get('custom_domain')
    if not domain or domain['status']!='AVAILABLE':blockers.append('Target API custom domain and mapping not ready')
    elif not any(m['ApiId']==target['api']['id'] and m['Stage']==c['API_STAGE'] and m.get('ApiMappingKey','')==c['API_MAPPING_KEY'] for m in domain['mappings']):
        blockers.append('Target public API mapping mismatch')
    if not raw.get('DNS_CHANGE_APPROVED'):blockers.append('DNS cutover approval missing')
    if not raw.get('ADDITIONAL_MONTHLY_BUDGET_USD'):blockers.append('Cutover cost allowance not reviewed')
    artifacts={'edge-update.json':configure_edge(edge,c),'frontend-public.json':public_config(c,target),
        'edge-parameters.json':{'OriginDomain':origin,'UiApiOriginDomain':api_host,'UiApiOriginPath':'' if c['API_STAGE']=='$default' else '/'+c['API_STAGE']},
        'routing-parameters.json':{'ApiTargetDomain':domain['target'] if domain else None,'ApiTargetZone':domain['target_zone'] if domain else None}}
    api_plan=api_domain_plan(c,target)
    if api_plan:artifacts['target-api-domain.json']=api_plan
    artifacts['external-dns-records.json']=external_records(c,source['frontend']['distribution_domain'],domain['target'] if domain else None)
    route=dns_template(c,source['frontend']['distribution_domain'])
    if route:artifacts['routing-update.json']=route
    folder=review_directory(out);hashes={}
    if folder.exists() and any(folder.iterdir()):raise ValueError('Use a fresh cutover review directory')
    for name,value in artifacts.items():write(folder/name,value);hashes[name]=hashlib.sha256((folder/name).read_bytes()).hexdigest()
    review={'mode':'CUTOVER_PREPARED_NOT_EXECUTED','account_id':c['ACCOUNT_ID'],'primary_region':c['PRIMARY_REGION'],'shared_stack_region':c['SHARED_STACK_REGION'],
        'domain':c['ROOT_DOMAIN'],'existing_distribution_id':source['frontend']['distribution_id'],'allowed_dns_names':[c['FRONTEND_DOMAIN'],c['API_DOMAIN']]+([c['REDIRECT_DOMAIN']] if c.get('REDIRECT_DOMAIN') else []),
        'hosted_zone_id':c['ROUTE53_HOSTED_ZONE_ID'],'dns_change_approved':raw.get('DNS_CHANGE_APPROVED') is True,'same_public_frontend':c['frontend_url'],'same_public_api':c['api_url'],'blockers':blockers,'aws_mutations':0,'customer_environments_moved':0,
        'retire_source_allowed':False,'sha256':hashes,'rollback':'Fence writes and schedulers, reconcile data watermark and operations from both endpoints, then approve reverse routing. DNS reversal alone is not data rollback.'}
    write(folder/'review.json',review);return review

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('config','source','target','edge_template','readiness','out'):p.add_argument('--'+key.replace('_','-'),type=Path,required=True)
    a=p.parse_args();read=lambda x:json.loads(x.read_text(encoding='utf-8'))
    r=prepare(read(a.config),read(a.source),read(a.target),read(a.edge_template),read(a.readiness),a.out)
    print(json.dumps({'mode':r['mode'],'blockers':r['blockers'],'retire_source_allowed':False}))

if __name__=='__main__':main()
