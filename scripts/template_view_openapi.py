"""Add the read-only, owner-scoped and redacted actual-stack view contract."""
def extend(doc):
    schemas=doc['components']['schemas']
    schemas['EnvironmentTemplateView']={'type':'object','required':['environment_id','template_id','region','source','read_only','redacted','deployable','template','resources','retrieved_at','view_sha256','redaction_count','scope'],
        'properties':{'environment_id':{'type':'string'},'template_id':{'type':'string','enum':[f'T{i:02}' for i in range(1,10)]},'region':{'type':'string'},
            'source':{'type':'string','enum':['AWS_CLOUDFORMATION_ORIGINAL']},'read_only':{'type':'boolean','enum':[True]},
            'redacted':{'type':'boolean','enum':[True]},'deployable':{'type':'boolean','enum':[False]},
            'retrieved_at':{'type':'integer','format':'int64'},'view_sha256':{'type':'string','pattern':'^[a-f0-9]{64}$'},
            'scope':{'type':'string','enum':['DECLARED_STACK_NOT_LIVE_INVENTORY']},'redaction_count':{'type':'integer','minimum':0},
            'omitted_sections':{'type':'array','items':{'type':'string'}},'template':{'type':'object','additionalProperties':True},
            'resources':{'type':'array','items':{'type':'object','required':['logical_id','resource_type','service'],
                'properties':{key:{'type':'string'} for key in ['logical_id','resource_type','service']}}}}}
    doc['paths']['/environments/{environment_id}/template']={'get':{
        'operationId':'getEnvironmentCloudFormationTemplate','summary':'Read the owned environment original CloudFormation template, with a fail-closed redacted educational projection.',
        'description':'No stack/Region/format overrides or write operations. Reads persisted provenance and verifies AWS stack tags. Hides code, user data, defaults, environment variables, metadata, outputs and unreviewed values. This view is not deployable or a drift/current-inventory assertion. Missing/deleted templates are not reconstructed. No shared caching.',
        'security':[{'CognitoAccessToken':[]}], 'parameters':[{'in':'path','name':'environment_id','required':True,'schema':{'type':'string','pattern':'^env-[a-f0-9]{24}$'}}],
        'responses':{'200':{'description':'Redacted actual-stack educational view','content':{'application/json':{'schema':{'$ref':'#/components/schemas/EnvironmentTemplateView'}}}},
            **{str(code):{'description':description} for code,description in [(400,'Invalid query override'),(401,'Cognito JWT required'),(403,'Verified and enabled account required'),(404,'Not owned or original stack template unavailable'),(409,'Unknown provenance, unsupported format or mismatched stack tags'),(503,'Read permission or CloudFormation temporarily unavailable')]}}}}
