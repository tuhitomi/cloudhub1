"""Additive admin presentation/search contract."""
def extend(doc):
    get=doc['paths']['/admin/users']['get'];params=get.setdefault('parameters',[])
    params[:]=[p for p in params if p.get('name')!='q']
    params.append({'name':'q','in':'query','required':False,'schema':{'type':'string','maxLength':128},
        'description':'Case-insensitive literal substring of email, username or Cognito subject. Searches up to three provider pages per call. Follow next_cursor until null; search_complete=false means more pages remain. Reset cursor after changing q. Test-data visibility still applies.'})
    get['description']=get.get('description','')+' Search results include search_query, search_complete and directory_pages_scanned.' if 'directory_pages_scanned' not in get.get('description','') else get['description']
    env=doc['paths']['/admin/environments']['get']
    suffix=' Admin-only owner_email is resolved from the configured Cognito pool, not client input. It is display/search data; owner_id remains authorization authority. Unknown, legacy or unavailable identities have null email and owner_email_status. ListUsers is eventually consistent.'
    if suffix not in env.get('description',''):env['description']=env.get('description','')+suffix
    doc['components']['schemas']['AdminOwnerContact']={'type':'object','readOnly':True,'properties':{
        'owner_email':{'type':'string','nullable':True,'format':'email'},'owner_email_status':{'type':'string','enum':['FOUND','LEGACY_ID','UNAVAILABLE','UNRESOLVED','NOT_FOUND']}}}
    schemas=doc['components']['schemas']
    schemas['AdminEnvironmentList']={'allOf':[{'$ref':'#/components/schemas/EnvironmentList'},{'type':'object','properties':{
        'items':{'type':'array','items':{'allOf':[{'$ref':'#/components/schemas/Environment'},{'$ref':'#/components/schemas/AdminOwnerContact'}]}},
        'owner_directory_checked_at':{'type':'integer','readOnly':True}}}]}
    env['responses']['200']['content']['application/json']['schema']={'$ref':'#/components/schemas/AdminEnvironmentList'}
    schemas['AdminAccountSearchList']={'allOf':[{'$ref':'#/components/schemas/AccountList'},{'type':'object','properties':{
        'search_query':{'type':'string'},'search_complete':{'type':'boolean'},'directory_pages_scanned':{'type':'integer','minimum':1,'maximum':3}}}]}
    get['responses']['200']['content']['application/json']['schema']={'$ref':'#/components/schemas/AdminAccountSearchList'}
