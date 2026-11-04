"""Additive account-wallet contract; keep legacy effective admission fields."""
def extend(doc):
    s=doc['components']['schemas'];integer={'type':'integer','minimum':0}
    props={k:dict(integer) for k in ['schema','granted_milliusd','committed_milliusd','balance_milliusd','overcommitted_milliusd','future_reserved_milliusd','accrued_estimate_milliusd','legacy_unreconciled_milliusd','unreserved_estimate_milliusd']}
    props.update(schema={'type':'integer','enum':[1]},currency={'type':'string','enum':['USD']},scope={'type':'string','enum':['ACCOUNT_LIFETIME_FORECAST']},
                 is_money={'type':'boolean','enum':[False]},is_aws_credit={'type':'boolean','enum':[False]},updated_at={'type':'integer','nullable':True})
    s['ForecastWallet']={'type':'object','additionalProperties':False,'required':list(props),'properties':props,
        'description':'Owner-only virtual forecast credits. Balance = max(0, allocation - owner committed forecast); other accounts do not debit this wallet. Not money, an AWS credit grant, or a promise of capacity. Historical/unknown amounts remain committed. No monthly reset.'}
    limits=s['Limits'];p=limits['properties']
    p.update(wallet={'$ref':'#/components/schemas/ForecastWallet'},user_remaining_milliusd=dict(integer),platform_budget={
        'type':'object','additionalProperties':False,'required':['remaining_milliusd','scope','is_aws_credits'],'properties':{
        'remaining_milliusd':dict(integer),'scope':{'type':'string','enum':['SHARED_AWS_FORECAST']},'is_aws_credits':{'type':'boolean','enum':[False]}}})
    p['remaining_milliusd']={**integer,'deprecated':True,'description':'Legacy effective admission headroom: minimum of personal wallet balance and shared platform headroom. Never label this as the personal wallet balance.'}
    p.update(budget_cycle={'type':'string','enum':['PROJECT_LIFETIME']},forecast={'type':'object'},aws_actual={'type':'object'},retained_resource_costs={'type':'string'})
    s['QuotaInput']['properties']['budget_milliusd']['description']='Absolute total allocation of virtual forecast credits, not an additional deposit. Existing usage/reservations remain; shared AWS budget is unchanged. New account fallback is 10000 (=USD 10). Admin defaults override the fallback.'
    s['PublicSignupPolicy']['properties']['wallet_scope']={'type':'string','enum':['ACCOUNT_LIFETIME_FORECAST']}
    doc['paths']['/limits']['get']['description']='JWT owner-only limits and personal forecast wallet; no client-provided owner selector. Personal balance and shared platform gate are separate. Legacy remaining_milliusd stays conservative for older clients.'
    doc['paths']['/admin/users/{owner_id}/limits']['post']['description']+=' Sets the absolute wallet allocation with audit, preserving all forecast history and shared counters. Does not transfer real funds or increase the platform budget.'
    doc['paths']['/admin/signup-defaults']['post']['description']+=' Applies to future initialized accounts only. Existing wallets and history are not reset.'
    error=s['Error']['properties'].get('error',{}).get('properties')
    if error is not None:
        error.update(budget_scope={'type':'string','enum':['ACCOUNT_WALLET','PLATFORM']},**{k:dict(integer) for k in ['required_milliusd','wallet_balance_milliusd','platform_remaining_milliusd']})
