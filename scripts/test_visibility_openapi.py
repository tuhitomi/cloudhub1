"""Additive presentation contract, without changing lifecycle or authentication."""
def extend(doc):
    for path in ['/environments','/admin/environments','/admin/users']:
        get=doc['paths'][path]['get']
        params=get.setdefault('parameters',[])
        params[:]=[p for p in params if p.get('name')!='include_test']
        params.append({'name':'include_test','in':'query','required':False,'schema':{'type':'boolean','default':False},
            'description':'Show explicitly classified test records hidden by default. Owner/admin authorization remains required; does not delete data or alter wallet/ledger calculations. Active/problem environments and enabled accounts are never hidden.'})
        suffix=' Lists return hidden_test_count and test_data_included. Environment lists also return retained_test_report_count: historical reports mentioning retained resources/backups, not a fresh AWS resource audit.'
        if suffix not in get.get('description',''):get['description']=get.get('description','')+suffix
    doc['components']['schemas']['TestDataPresentation']={'type':'object','description':'Operator-reviewed metadata only, never accepted as client authority for hiding data.',
        'properties':{'schema':{'type':'integer','enum':[1]},'classification':{'type':'string','enum':['TEST']},
            'hidden_by_default':{'type':'boolean'},'archived_at':{'type':'integer'},'evidence':{'type':'string'}}}
