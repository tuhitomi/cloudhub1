"""Read-only CloudFormation education route; no user-supplied AWS resource IDs."""
from copy import deepcopy
PATH='/environments/{environment_id}/template'

def policy(template):
    template['Resources']['TemplateViewReadPolicy']={'Type':'AWS::IAM::ManagedPolicy','Properties':{
        'Description':'Read only CloudHub environment stack templates in the three allowed Regions; backend verifies owner and redacts all unreviewed fields.',
        'Roles':[{'Ref':'ApiFunctionRole'}], 'PolicyDocument':{'Version':'2012-10-17','Statement':[{
            'Effect':'Allow','Action':['cloudformation:DescribeStacks','cloudformation:GetTemplate'],
            'Resource':[{'Fn::Sub':'arn:${AWS::Partition}:cloudformation:'+region+':${AWS::AccountId}:stack/cloudhub-env-*/*'} for region in ('ap-southeast-1','ap-northeast-1','us-east-1')]}]}}}

def extend(template):
    policy(template)
    template['Resources']['ApiFunction']['Properties']['Events']['TemplateView']={'Type':'HttpApi','Properties':{
        'ApiId':{'Ref':'HttpApi'},'Method':'GET','Path':PATH,
        'RouteSettings':{'ThrottlingRateLimit':1,'ThrottlingBurstLimit':2}}}

def extend_native(template):
    if template['Resources']['ApiFunction']['Type']!='AWS::Lambda::Function':raise ValueError('Expected native template')
    policy(template);resources=template['Resources'];paths=resources['HttpApi']['Properties']['Body']['paths']
    spec=deepcopy(paths['/environments/{environment_id}']['get']);assert spec.get('security')
    if PATH in paths and paths[PATH].get('get')!=spec:raise ValueError('Existing template route differs')
    paths[PATH]={'get':spec}
    resources['HttpApiApiGatewayDefaultStage']['Properties'].setdefault('RouteSettings',{})['GET '+PATH]={'ThrottlingRateLimit':1,'ThrottlingBurstLimit':2}
    resources['TemplateViewInvoke']={'Type':'AWS::Lambda::Permission','Properties':{
        'Action':'lambda:InvokeFunction','FunctionName':{'Fn::GetAtt':['ApiFunction','Arn']},
        'Principal':'apigateway.amazonaws.com','SourceAccount':{'Ref':'AWS::AccountId'},
        'SourceArn':{'Fn::Sub':'arn:${AWS::Partition}:execute-api:${AWS::Region}:${AWS::AccountId}:${HttpApi}/*/GET/environments/*/template'}}}
    return template
