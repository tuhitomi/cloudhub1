"""Additive maintenance routes and one-object static publication permission."""
from copy import deepcopy
ROUTES=[('GET','/admin/announcements'),('POST','/admin/announcements'),('GET','/admin/announcements/{announcement_id}'),
        ('PUT','/admin/announcements/{announcement_id}')]+[('POST','/admin/announcements/{announcement_id}/'+action) for action in ['preview','publish','cancel','retry']]

def common(template):
    template['Parameters']['MaintenancePublicEnabled']={'Type':'String','Default':'false','AllowedValues':['true','false'],
        'Description':'Enable admin-reviewed static maintenance notices only after the scoped one-object S3 permission is reviewed.'}
    template.setdefault('Conditions',{})['MaintenancePublicOn']={'Fn::Equals':[{'Ref':'MaintenancePublicEnabled'},'true']}
    resources=template['Resources']
    for name in ['ApiFunction','SweepFunction']:
        resources[name]['Properties']['Environment']['Variables']['MAINTENANCE_PUBLIC_ENABLED']={'Ref':'MaintenancePublicEnabled'}
    bucket='FrontendBucket'
    if bucket not in resources:
        bucket='MaintenanceFrontendBucket'
        template['Parameters'][bucket]={'Type':'String','Default':'','Description':'Existing owned static bucket; required before enabling maintenance public notices for external hosting.'}
    resources['SweepFunction']['Properties']['Environment']['Variables']['MAINTENANCE_FRONTEND_BUCKET']={'Ref':bucket}
    resources['MaintenancePublicPolicy']={'Type':'AWS::IAM::ManagedPolicy','Condition':'MaintenancePublicOn','Properties':{
        'Description':'Read/write exactly the owned maintenance.json. No bucket listing, asset modification, public bucket or delete permission.',
        'Roles':[{'Ref':'SweepFunctionRole'}],'PolicyDocument':{'Version':'2012-10-17','Statement':[{
            'Effect':'Allow','Action':['s3:GetObject','s3:PutObject'],'Resource':{'Fn::Sub':'arn:${AWS::Partition}:s3:::${'+bucket+'}/maintenance.json'},
            'Condition':{'StringEquals':{'s3:ResourceAccount':{'Ref':'AWS::AccountId'}}}}]}}}

def extend(template):
    common(template)
    for index,(method,path) in enumerate(ROUTES):
        template['Resources']['ApiFunction']['Properties']['Events']['MaintenanceRoute'+str(index)]={'Type':'HttpApi','Properties':{
            'ApiId':{'Ref':'HttpApi'},'Method':method,'Path':path,'RouteSettings':{'ThrottlingRateLimit':1,'ThrottlingBurstLimit':2}}}

def extend_native(template):
    if template['Resources']['ApiFunction']['Type']!='AWS::Lambda::Function':raise ValueError('Expected native template')
    common(template);resources=template['Resources'];paths=resources['HttpApi']['Properties']['Body']['paths']
    example=paths['/admin/notifications']['get'];assert example.get('security')
    for index,(method,path) in enumerate(ROUTES):
        old=paths.setdefault(path,{}).get(method.lower())
        if old is not None and old!=example:raise ValueError('Existing route differs; review before replacement')
        paths[path][method.lower()]=deepcopy(example)
        resources['HttpApiApiGatewayDefaultStage']['Properties'].setdefault('RouteSettings',{})[method+' '+path]={'ThrottlingRateLimit':1,'ThrottlingBurstLimit':2}
    # Bound to this API/account and announcement paths only. HTTP methods remain
    # governed by the eight JWT routes; avoids exhausting Lambda's 20 KiB policy.
    for index,path in enumerate(['/admin/announcements','/admin/announcements/*']):
        resources['MaintenanceInvoke'+str(index)]={'Type':'AWS::Lambda::Permission','Properties':{'Action':'lambda:InvokeFunction',
            'FunctionName':{'Fn::GetAtt':['ApiFunction','Arn']},'Principal':'apigateway.amazonaws.com','SourceAccount':{'Ref':'AWS::AccountId'},
            'SourceArn':{'Fn::Sub':'arn:${AWS::Partition}:execute-api:${AWS::Region}:${AWS::AccountId}:${HttpApi}/*/*'+path}}}
    return template
