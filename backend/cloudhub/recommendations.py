"""F03: capability-filtered planning, with separate demand and evidence."""
from copy import deepcopy
from decimal import Decimal
import re
from .catalog import ACTIVE_TEMPLATES
from .errors import HubError
from .workloads import normalize,demand,resource_assessment,schema as workload_schema,VERSION,BASIC_DEFAULTS
from .benchmarks import matching,policy,capability_revision
from .operating_policy import validate_policy,plan

def schema(service):
    service.refresh_pricing(cached=True)
    result=workload_schema();result.update(default_region=service.region_registry().home,estimate_hours=[1,2,4,8],
        policy=policy(service),quote_and_confirmation_required=True)
    for tid,row in result['templates'].items():
        row['regions']=service.region_options(tid)
        for region in row['regions']:
            for option in region['configuration_options']:
                option['operating_modes']=['AUTO_OFF','AUTO_RENEW']+(['CONTINUOUS'] if service.continuous_available({'template_id':tid,'region':region['region'],'configuration':option['configuration']}) else [])
                option['capability_revision']=capability_revision(tid,option['configuration'])
    return result

def validate(body):
    allowed={'mode','template_id','region','profile_id','estimate_hours','budget_milliusd','operating_policy','workload','application_revision','scenario_revision'}
    if not isinstance(body,dict) or set(body)-allowed or not {'mode','template_id','region','estimate_hours','workload'}<=body.keys():raise HubError('RECOMMENDATION_INVALID','Use the published planning contract.')
    tid=body['template_id']
    if tid not in ACTIVE_TEMPLATES:raise HubError('TEMPLATE_UNAVAILABLE','Choose T01–T09.',409)
    if body['mode'] not in {'RECOMMEND','ASSESS'}:raise HubError('RECOMMENDATION_INVALID','Choose recommend or assess.')
    if type(body['estimate_hours']) is not int or body['estimate_hours'] not in {1,2,4,8}:raise HubError('RECOMMENDATION_INVALID','Choose a supported planning horizon.')
    budget=body.get('budget_milliusd')
    if budget is not None and (type(budget) is not int or not 0<=budget<=10**9):raise HubError('RECOMMENDATION_INVALID','Budget must be integer milliUSD or null.')
    for key in ['application_revision','scenario_revision']:
        if body.get(key) is not None and (not isinstance(body[key],str) or not re.fullmatch('[a-f0-9]{64}',body[key])):raise HubError('RECOMMENDATION_INVALID','Use a revision SHA-256 or Unknown.',details={'field':key})
    if body['mode']=='ASSESS' and not isinstance(body.get('profile_id'),str):raise HubError('RECOMMENDATION_INVALID','Choose the configuration to assess.')
    w=normalize(tid,body['workload'])
    if tid=='T04' and w['peak_users'] is not None and w['active_users'] is not None and w['peak_users']<w['active_users']:raise HubError('WORKLOAD_CONFLICT','Peak usage cannot be below normal usage.',details={'field':'peak_users'})
    return w

def recommend(service,owner,body):
    workload=validate(body);tid=body['template_id'];service.refresh_pricing(cached=True)
    region=service.region_registry().select(body['region']);hours=body['estimate_hours'];selected=body.get('profile_id')
    published=next(r for r in service.region_options(tid) if r['region']==region)
    if selected and not any(p['id']==selected for p in published['configuration_options']):raise HubError('INVALID_CONFIGURATION','Choose a published configuration.')
    draft=body.get('operating_policy',{'mode':'AUTO_OFF','period_minutes':60,'ending_policy':'BACKUP_RETIRE','budget_limit_milliusd':None})
    if not isinstance(draft,dict) or 'confirmed' in draft:raise HubError('RECOMMENDATION_INVALID','Recommendations do not collect final lifecycle consent.')
    operating=validate_policy(tid,{**draft,'confirmed':True});settings=policy(service);candidates=[];excluded=[];assessment=None
    needs=demand(tid,workload,hours)
    for profile in published['configuration_options']:
        cfg=profile['configuration'];reason=None
        if not profile['verification_passed'] or not profile['enabled'] or profile.get('disabled_reason'):reason='CONFIGURATION_UNAVAILABLE'
        if operating['mode']=='CONTINUOUS' and not service.continuous_available({'template_id':tid,'region':region,'configuration':cfg}):reason='CONTINUOUS_UNAVAILABLE'
        if reason:
            excluded.append({'profile_id':profile['id'],'code':reason})
            if selected==profile['id']:assessment={'profile_id':selected,'status':reason,'capacity':None,'configuration':cfg}
            continue
        resource=resource_assessment(tid,cfg,workload,settings['resource_headroom_percent'],hours)
        # These are deployment settings from the existing T09 IaC, not measured
        # throughput. The account concurrency ceiling is separately snapshotted.
        if tid=='T09':
            quota=settings['observed_quotas'];ceiling=quota.get('lambda_account_concurrency') if quota.get('region')==region else None
            if ceiling is not None and needs.get('required_concurrency') is not None and Decimal(needs['required_concurrency'])>ceiling:resource['failures'].append({'code':'ACCOUNT_CONCURRENCY_LIMIT','field':'processing_ms','available':ceiling,'component':'shared Lambda account quota'})
        if resource['failures']:resource['status']='NOT_FIT'
        forecast=plan(service.estimator_for(region),tid,hours,operating,cfg,workload=workload)
        cost=forecast['preview'];total=cost['total_milliusd'];budget=body.get('budget_milliusd')
        budget_status='UNKNOWN' if not cost['approved'] or total is None else 'NOT_SET' if budget is None else 'WITHIN' if total<=budget else 'EXCEEDED'
        policy_budget='NOT_SET'
        if operating['mode']=='AUTO_RENEW':
            policy_budget='UNKNOWN' if not forecast['approved'] else 'WITHIN' if forecast['total_milliusd']<=operating['budget_limit_milliusd']<=service.budget else 'EXCEEDED'
        matched,stale=matching(service,owner,tid,region,cfg,workload,body.get('application_revision'),body.get('scenario_revision'))
        evidence=matched[0] if matched else None
        level=evidence['evidence_level'] if evidence else 'RESOURCE_REQUIREMENTS' if resource['status']=='RESOURCE_FIT' else 'INSUFFICIENT_DATA'
        performance='OBSERVED_WITH_ERRORS' if evidence and evidence['metrics']['errors'] else 'OBSERVED_IN_RECORDED_SCOPE' if evidence else 'NOT_MEASURED'
        selection_blockers=(['RESOURCE_NOT_FIT'] if resource['status']=='NOT_FIT' else [])+(['PRICE_INCOMPLETE'] if not forecast['approved'] else [])+(['BUDGET_EXCEEDED'] if budget_status=='EXCEEDED' or policy_budget=='EXCEEDED' else [])
        option={'template_id':tid,'region':region,'profile_id':profile['id'],'configuration':cfg,'resource_assessment':resource,'selection_blockers':selection_blockers,
            'status':resource['status'],'evidence_level':level,'capacity':evidence['metrics'] if evidence else None,'benchmark':evidence,
            'excluded_evidence':stale,'performance_status':performance,'budget_status':budget_status,'cost':cost,
            'first_period':forecast['first_period'],'renewal_period':forecast['renewal_period'],'after_shutdown':forecast['after_shutdown'],
            'policy_budget_status':policy_budget,
            'can_select':bool(resource['status']!='NOT_FIT' and forecast['approved'] and budget_status!='EXCEEDED' and policy_budget not in {'EXCEEDED','UNKNOWN'}),
            'reason_keys':['rec.reason.resourceOnly' if not evidence else 'rec.reason.measured','rec.reason.freshQuote'],
            'growth_components':[],'roles':[],
            'creation_defaults':{'template_id':tid,'region':region,'configuration':cfg,'profile_id':profile['id'],'estimate_hours':hours,
                'operating_policy':draft,'planning_workload':workload}}
        if selected==profile['id']:assessment=deepcopy(option)
        if resource['status']=='NOT_FIT':excluded.append({'profile_id':profile['id'],'code':'RESOURCE_NOT_FIT','details':resource['failures']})
        else:candidates.append(option)
    # No fabricated triplet. One card may carry economical/recommended labels;
    # another is growth reserve only for the resource components that differ.
    profile_order={p['id']:i for i,p in enumerate(published['configuration_options'])}
    candidates.sort(key=lambda c:(not c['can_select'],c['evidence_level'] not in {'APPLICATION_VERIFIED','SAMPLE_APPLICATION'},c['cost']['total_milliusd'] is None,c['cost']['total_milliusd'] or 0,profile_order[c['profile_id']]))
    selectable=[c for c in candidates if c['can_select']]
    if selectable:
        economical=min(selectable,key=lambda c:c['cost']['total_milliusd']);economical['roles'].append('ECONOMICAL');selectable[0]['roles'].append('RECOMMENDED')
        reference=selectable[0]['configuration']
        for option in selectable[1:]:
            increased=[k for k,v in option['configuration'].items() if type(v) is int and type(reference.get(k)) is int and v>reference[k]]
            if increased:option['growth_components']=increased;option['roles'].append('GROWTH_RESERVE')
    return {'schema':VERSION,'mode':body['mode'],'template_id':tid,'region':region,'estimate_hours':hours,
        'generated_at':int(service.clock()),'read_only':True,'is_quote':False,'admission_checked':False,'workload':workload,'demand':needs,
        'options':candidates,'assessment':assessment,'excluded':excluded,'status':'OPTIONS' if selectable else 'NO_MATCH',
        'input_assumptions':{k:v for k,v in BASIC_DEFAULTS.get(tid,{}).items() if body['workload'].get(k) is None},
        'policy':settings,'safety_keys':['rec.safety.demandNotCapacity','rec.safety.notAvailability','rec.reason.freshQuote'],
        'request_fingerprint':__import__('cloudhub.quotes',fromlist=['fingerprint']).fingerprint(body)}
