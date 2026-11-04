"""Read-only, allowlisted product information; never issues a quote or reserves quota."""
from .catalog import ACTIVE_TEMPLATES,catalog
from .registration import defaults
from .errors import HubError

CONFIG_KEYS={'instance_type','root_gib','data_gib','db_class','db_gib','min_instances','max_instances',
 'max_records','max_record_bytes','max_files','max_file_bytes','max_total_bytes','max_writes',
 'cpu','memory_mib','tasks','nodes','efs_encrypted','billing','lambda_memory_mib'}
ESTIMATE_KEYS={'currency','region','price_updated_at','approved','total_milliusd','units','unit_regions',
 'lines','assumptions','contingency_percent'}

def hardware(configuration):
    result={k:v for k,v in configuration.items() if k in CONFIG_KEYS}
    if result.get('instance_type')=='t3.micro':
        result.update(vcpu_per_instance=2,memory_gib_per_instance=1)
    return result

def read(service,query=None):
    query=query or {}
    if set(query)-{'template_id','region','profile_id','hours'}:
        raise HubError('INVALID_INPUT','Unsupported public catalog query.')
    if query and (not {'template_id','region','profile_id'}<=query.keys() or query['template_id'] not in ACTIVE_TEMPLATES):
        raise HubError('INVALID_INPUT','Select a published template, Region and configuration.')
    if str(query.get('hours','1')) not in {'1','4','8'}:
        raise HubError('INVALID_INPUT','Public preview supports 1, 4 or 8 hours.')
    service.refresh_pricing(cached=True)
    items=[]
    for row in catalog(service.verified):
        regions=[]
        for region in service.region_options(row['template_id']):
            regions.append({'region':region['region'],'status':region['status'],'configuration_options':[
                {'id':p['id'],'configuration':hardware(p['configuration']),
                 'status':p['status'],'create_enabled':bool(p['create_enabled'])}
                for p in region['configuration_options']]})
        items.append({'template_id':row['template_id'],'services':row['services'],'regions':regions})
    result={'read_only':True,'requires_login_to_create':True,'generated_at':int(service.clock()),
        'default_region':service.region_registry().home,'items':items,
        'signup_policy':{**defaults(service),'budget_scope':'PROJECT_LIFETIME_FORECAST',
            'wallet_scope':'ACCOUNT_LIFETIME_FORECAST',
            'aws_credit_grant':False,'email_verification_required':True,'policy_may_change':True}}
    if query:
        region=service.region_registry().select(query['region'])
        row=next(t for t in items if t['template_id']==query['template_id'])
        choice=next((p for r in row['regions'] if r['region']==region for p in r['configuration_options'] if p['id']==query['profile_id']),None)
        if not choice:raise HubError('INVALID_CONFIGURATION','Choose a published configuration.')
        # Resolve the original approved configuration; hardware metadata is never
        # passed into the estimator or the authenticated creation contract.
        original=next(p['configuration'] for r in service.region_options(row['template_id']) if r['region']==region for p in r['configuration_options'] if p['id']==choice['id'])
        estimator=service.estimator_for(region)
        estimate=estimator.estimate(row['template_id'],int(query.get('hours','1')),configuration=original)
        result={k:v for k,v in result.items() if k!='items'}
        result['preview']={'template_id':row['template_id'],'region':region,'profile_id':choice['id'],
            'configuration':choice['configuration'],'status':choice['status'],'create_enabled':choice['create_enabled'],
            'hours':int(query.get('hours','1')),'indicative_only':True,'is_quote':False,
            'estimate':{k:v for k,v in estimate.items() if k in ESTIMATE_KEYS},
            'after_shutdown':estimator.holding(row['template_id'],'BACKUP_RETIRE',original)}
    return result
