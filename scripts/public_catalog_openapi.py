"""Public product metadata only; all account/quote/lifecycle routes retain JWT."""
def extend(doc):
 s=doc['components']['schemas']
 s['PublicSignupPolicy']={'type':'object','additionalProperties':False,'required':['max_active','budget_milliusd','budget_scope','aws_credit_grant','email_verification_required','policy_may_change'],'properties':{
  'max_active':{'type':'integer','minimum':0},'budget_milliusd':{'type':'integer','minimum':0},
  'budget_scope':{'type':'string','enum':['PROJECT_LIFETIME_FORECAST']},'aws_credit_grant':{'type':'boolean','enum':[False]},
  'email_verification_required':{'type':'boolean','enum':[True]},'policy_may_change':{'type':'boolean','enum':[True]}}}
 s['PublicCatalog']={'type':'object','required':['read_only','requires_login_to_create','generated_at','default_region','signup_policy'],'properties':{
  'read_only':{'type':'boolean','enum':[True]},'requires_login_to_create':{'type':'boolean','enum':[True]},'generated_at':{'type':'integer'},
  'default_region':{'type':'string','enum':['ap-southeast-1','ap-northeast-1','us-east-1']},'signup_policy':{'$ref':'#/components/schemas/PublicSignupPolicy'},
  'items':{'type':'array','maxItems':9,'items':{'type':'object','required':['template_id','services','regions'],'properties':{
   'template_id':{'type':'string','pattern':'^T0[1-9]$'},'services':{'type':'array','items':{'type':'string'}},'regions':{'type':'array','maxItems':3,'items':{'type':'object'}}}}},
  'preview':{'type':'object','required':['template_id','region','profile_id','hours','configuration','estimate','indicative_only','is_quote','status','after_shutdown'],'properties':{
   'template_id':{'type':'string','pattern':'^T0[1-9]$'},'region':{'type':'string'},'profile_id':{'type':'string'},'hours':{'type':'integer','enum':[1,4,8]},
   'configuration':{'type':'object'},'estimate':{'type':'object','description':'Region-specific approved unit prices, assumptions, first-period cost and 20% contingency. Null amount when unavailable.'},
   'after_shutdown':{'type':'object'},'status':{'type':'string','enum':['SUPPORTED','VERIFYING','UNAVAILABLE']},'create_enabled':{'type':'boolean'},
   'indicative_only':{'type':'boolean','enum':[True]},'is_quote':{'type':'boolean','enum':[False]}}}}}
 params=[]
 for name,values in [('template_id',[f'T0{i}' for i in range(1,10)]),('region',['ap-southeast-1','ap-northeast-1','us-east-1']),('profile_id',['standard','expanded','files']),('hours',['1','4','8'])]:
  params.append({'in':'query','name':name,'required':False,'schema':{'type':'string','enum':values},'description':'For a detail preview supply template_id, region and profile_id together. hours defaults to 1.'})
 doc['paths']['/public/catalog']={'get':{'operationId':'getPublicProductCatalog','security':[],'parameters':params,
  'description':'Unauthenticated allowlisted product metadata. No request body, owner selector, quote, reservation, resource identifier, account data or credentials. GET only. Query-free response has all T01–T09 and current signup defaults. Detail preview uses the existing regional estimator. Amounts are indicative and cannot authorize creation. All responses use Cache-Control: no-store.',
  'responses':{'200':{'description':'Public product metadata or indicative detail preview.','content':{'application/json':{'schema':{'$ref':'#/components/schemas/PublicCatalog'}}}},
   '400':{'description':'Invalid/incomplete query.'},'409':{'description':'Region or configuration is not allowed.'},'503':{'description':'Reference data temporarily unavailable; no state was changed.'}}}}
