def extend(paths,schemas,operation,response,ref):
    region={'type':'string','enum':['ap-southeast-1','ap-northeast-1','us-east-1'],'description':'Commercial AWS Region. Allowed template/configuration combinations come from /templates or /regions. Immutable after create.'}
    for name in ['CreateInput','EstimateInput']:schemas[name]['properties']['region']=region
    schemas['Estimate']['properties']['unit_regions']={'type':'object','readOnly':True,
        'description':'Price location for each used unit. Shared management components can stay in the control Region; CloudFront units are global.',
        'additionalProperties':{'type':'string','enum':region['enum']+['global']}}
    schemas['Estimate']['properties']['price_updated_at']['nullable']=True
    schemas['HoldingEstimate']={'type':'object','required':['approved','currency','region','total_milliusd','period_hours'],'properties':{
        'approved':{'type':'boolean'},'currency':{'type':'string','enum':['USD']},'region':region,
        'total_milliusd':{'type':'integer','nullable':True},'period_hours':{'type':'integer'},'units':{'type':'object'},
        'storage_gib':{'type':'object'},'unknown':{'type':'array','items':{'type':'string'}}}}
    schemas['CostPlan']={'type':'object','required':['template_id','approved','currency','preview','first_period','renewal_period','after_shutdown'],'properties':{
        'template_id':{'type':'string'},'approved':{'type':'boolean'},'currency':{'type':'string','enum':['USD']},'region':region,
        'configuration':{'type':'object'},'operating_policy':ref('OperatingPolicyRead'),'estimate_hours':{'type':'integer'},
        **{key:ref('Estimate') for key in ('preview','first_period','renewal_period')},'after_shutdown':ref('HoldingEstimate'),
        'initial_commitment_milliusd':{'type':'integer','nullable':True},'total_milliusd':{'type':'integer','nullable':True},
        'budget_scope':{'type':'string'},'budget_is_aws_billing_cap':{'type':'boolean','enum':[False]},
        'configuration_verified':{'type':'boolean'},'budget_feasible':{'type':'boolean'},'unknown':{'type':'array','items':{'type':'string'}}}}
    paths['/estimates']['post']['responses']['200']={'description':'Regional estimate or lifecycle cost plan; USD is never converted by language.',
        'content':{'application/json':{'schema':{'oneOf':[ref('Estimate'),ref('CostPlan')]}}}}
    for name in ['Environment','Operation','RecoveryPoint','Resource']:
        schemas[name]['properties']['region']={**region,'readOnly':True}
    schemas['Resource']['properties']['region']={'type':'string','description':'AWS Region or global for IAM/CloudFront.'}
    languages=['en','vi','ja','ko','zh-Hans','fr','de','es']
    schemas['LanguagePreference']={'type':'object','additionalProperties':False,'required':['language'],'properties':{'language':{'type':'string','enum':languages+['auto']}}}
    schemas['UiContext']={'type':'object','required':['country_code','suggested_language','source','default_language','supported_languages'],'properties':{
        'country_code':{'type':'string','nullable':True,'pattern':'^[A-Z]{2}$'},'suggested_language':{'type':'string','enum':languages},
        'supported_languages':{'type':'array','items':{'type':'string','enum':languages}},'default_language':{'type':'string','enum':['en']},
        'source':{'type':'string','enum':['cloudfront','unavailable']}}}
    paths['/regions']={'get':operation('listRegions')}
    paths['/account/preferences']={'put':operation('saveLanguagePreference','put','LanguagePreference')}
    paths['/ui-context']={'get':{'operationId':'getUiContext','security':[],'description':'Public country-only context. Call through the same-origin CloudFront route. A direct API request cannot supply trusted geography. No shared caching or account data.',
        'responses':{'200':response('Country context','UiContext')}}}
    schemas['Environment']['properties']['region_status']={'type':'string','enum':['VERIFICATION_REQUIRED'],'readOnly':True}
