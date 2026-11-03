"""Optional owner-isolated email permissions. Default off; review before enabling."""
from copy import deepcopy

ROUTES=[('POST','/notifications/{notification_id}/read'),('GET','/account/notification-preferences'),
        ('POST','/account/notification-preferences'),('POST','/account/notification-preferences/check')]


def extend_native_routes(template):
    """Patch an existing native template, including Gateway invoke permissions.

    SAM creates these permissions for Events. An additive native-template rollout
    must add them explicitly; a route with JWT alone cannot invoke Lambda.
    """
    resources=template['Resources']
    if resources['ApiFunction']['Type']!='AWS::Lambda::Function':
        raise ValueError('Expected an inventoried native Lambda template, not SAM source')
    body=resources['HttpApi']['Properties']['Body']
    example=body['paths']['/notifications']['get']
    if not example.get('security'):
        raise ValueError('Existing notification route must require JWT')
    stage=resources['HttpApiApiGatewayDefaultStage']['Properties']
    for index,(method,path) in enumerate(ROUTES):
        operation=deepcopy(example)
        current=body['paths'].setdefault(path,{}).get(method.lower())
        if current is not None and current!=operation:raise ValueError('Existing route differs; review before replacement')
        body['paths'][path][method.lower()]=operation
        stage.setdefault('RouteSettings',{})[method+' '+path]={'ThrottlingRateLimit':2,'ThrottlingBurstLimit':4}
        invoke={'Type':'AWS::Lambda::Permission','Properties':{'Action':'lambda:InvokeFunction',
            'FunctionName':{'Fn::GetAtt':['ApiFunction','Arn']},'Principal':'apigateway.amazonaws.com',
            'SourceAccount':{'Ref':'AWS::AccountId'},'SourceArn':{'Fn::Sub':
                'arn:${AWS::Partition}:execute-api:${AWS::Region}:${AWS::AccountId}:${HttpApi}/*/'+method+path.replace('{notification_id}','*')}}}
        name='UserNotificationInvoke'+str(index)
        if name in resources and resources[name]!=invoke:raise ValueError('Existing invoke permission differs')
        resources[name]=invoke
    return template

def extend(template):
    params,resources=template['Parameters'],template['Resources']
    params['UserNotificationEmailEnabled']={'Type':'String','Default':'false','AllowedValues':['true','false'],
        'Description':'Opt-in user email topics only after scoped SNS IAM and cost approval. Separate from operator alerts.'}
    params['NotificationFrontendOrigin']={'Type':'String','Default':'','AllowedPattern':'^$|https://[a-zA-Z0-9.-]+',
        'Description':'Public frontend origin for links; required when user email is enabled. No token/query/path.'}
    template.setdefault('Conditions',{})['UserNotificationEmailOn']={'Fn::Equals':[{'Ref':'UserNotificationEmailEnabled'},'true']}
    template.setdefault('Rules',{})['UserNotificationOriginRequired']={'RuleCondition':{'Fn::Equals':[{'Ref':'UserNotificationEmailEnabled'},'true']},
        'Assertions':[{'Assert':{'Fn::Not':[{'Fn::Equals':[{'Ref':'NotificationFrontendOrigin'},'']}]},'AssertDescription':'Enabled user email requires a public frontend HTTPS origin.'}]}
    topic={'Fn::Sub':'arn:${AWS::Partition}:sns:${AWS::Region}:${AWS::AccountId}:${AWS::StackName}-user-notice-*'}
    prefix={'Fn::Sub':'${AWS::StackName}-user-notice-'}
    for name in ('ApiFunction','SweepFunction'):
        resources[name]['Properties']['Environment']['Variables'].update(USER_NOTIFICATION_EMAIL_ENABLED={'Ref':'UserNotificationEmailEnabled'},
            NOTIFICATION_ACCOUNT_ID={'Ref':'AWS::AccountId'},USER_NOTIFICATION_TOPIC_PREFIX=prefix,
            NOTIFICATION_FRONTEND_ORIGIN={'Ref':'NotificationFrontendOrigin'})
    policy=lambda actions,condition=None:dict({'Effect':'Allow','Action':actions,'Resource':topic},**({'Condition':condition} if condition else {}))
    api=[policy(['sns:CreateTopic','sns:TagResource'],{'StringEquals':{'aws:RequestTag/cloudhub:managed':'true','aws:RequestTag/cloudhub:purpose':'user-notifications'}}),
         policy('sns:Subscribe',{'StringEquals':{'sns:Protocol':'email'}}),policy('sns:ListSubscriptionsByTopic')]
    sweep=[policy(['sns:ListSubscriptionsByTopic','sns:Publish']),{'Effect':'Allow','Action':'cognito-idp:AdminGetUser',
        'Resource':{'Fn::Sub':'arn:${AWS::Partition}:cognito-idp:${AWS::Region}:${AWS::AccountId}:userpool/${UserPool}'}}]
    for name,role,statements in [('UserEmailApiPolicy','ApiFunctionRole',api),('UserEmailSweepPolicy','SweepFunctionRole',sweep)]:
        resources[name]={'Type':'AWS::IAM::ManagedPolicy','Condition':'UserNotificationEmailOn','Properties':{
            'Description':'Only CloudHub owner/address-isolated notification topics; never shared operator alert topic.',
            'Roles':[{'Ref':role}],'PolicyDocument':{'Version':'2012-10-17','Statement':statements}}}
    events=resources['ApiFunction']['Properties']['Events']
    for index,(method,path) in enumerate(ROUTES):
        events['UserNotificationRoute'+str(index)]={'Type':'HttpApi','Properties':{'ApiId':{'Ref':'HttpApi'},'Method':method,'Path':path,
            'RouteSettings':{'ThrottlingRateLimit':2,'ThrottlingBurstLimit':4}}}
