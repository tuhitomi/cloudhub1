"""Reliability and protection settings for the control plane.

1. Spend guard: AWS Budgets (actual monthly cost) -> SNS -> Lambda writes a
   freeze row that blocks spend-increasing admissions (see cloudhub.spend_guard).
   Off until MonthlyBudgetUsd > 0.
2. Tracing: AWS X-Ray on every Lambda function and the lifecycle state machine,
   so one operation can be followed API -> Step Functions -> worker -> AWS SDK.
3. Identity WAF: optional regional AWS WAF web ACL on the Cognito user pool
   (IP reputation list and a per-IP rate limit on sign-up/sign-in calls).
"""
import json

XRAY_ACTIONS = ['xray:PutTraceSegments', 'xray:PutTelemetryRecords', 'xray:GetSamplingRules',
                'xray:GetSamplingTargets', 'xray:GetSamplingStatisticSummaries']
IDENTITY_RATE_LIMIT = 100  # requests per IP in any 5-minute window


def ref(name): return {'Ref': name}
def sub(text): return {'Fn::Sub': text}
def att(name, key='Arn'): return {'Fn::GetAtt': [name, key]}


def visibility(name):
    return {'SampledRequestsEnabled': True, 'CloudWatchMetricsEnabled': True, 'MetricName': name}


def managed_rule(name, priority):
    return {'Name': name, 'Priority': priority, 'OverrideAction': {'None': {}},
            'Statement': {'ManagedRuleGroupStatement': {'VendorName': 'AWS', 'Name': name}},
            'VisibilityConfig': visibility(name)}


def rate_rule(limit, priority, name='PerIpRateLimit'):
    return {'Name': name, 'Priority': priority, 'Action': {'Block': {}},
            'Statement': {'RateBasedStatement': {'Limit': limit, 'AggregateKeyType': 'IP', 'EvaluationWindowSec': 300}},
            'VisibilityConfig': visibility(name)}


def spend_guard(params, conditions, resources):
    params['MonthlyBudgetUsd'] = {'Type': 'Number', 'Default': 0, 'MinValue': 0,
        'Description': 'Actual monthly AWS cost budget for this account. 0 disables the budget and spend guard.'}
    params['SpendGuardThresholdPercent'] = {'Type': 'Number', 'Default': 100, 'MinValue': 50, 'MaxValue': 200,
        'Description': 'Percent of MonthlyBudgetUsd (actual cost) at which new creations and renewals are frozen.'}
    conditions['HasSpendBudget'] = {'Fn::Not': [{'Fn::Equals': [ref('MonthlyBudgetUsd'), 0]}]}
    when = {'Condition': 'HasSpendBudget'}
    budget_name = sub('${AWS::StackName}-monthly')
    # No KMS key: AWS Budgets cannot publish to a topic encrypted with the
    # AWS managed SNS key, and the message carries no secrets.
    resources['SpendGuardTopic'] = {'Type': 'AWS::SNS::Topic', **when}
    resources['SpendGuardTopicPolicy'] = {'Type': 'AWS::SNS::TopicPolicy', **when, 'Properties': {
        'Topics': [ref('SpendGuardTopic')], 'PolicyDocument': {'Version': '2012-10-17', 'Statement': [{
            'Sid': 'AwsBudgetsPublish', 'Effect': 'Allow', 'Principal': {'Service': 'budgets.amazonaws.com'},
            'Action': 'SNS:Publish', 'Resource': ref('SpendGuardTopic'),
            'Condition': {'StringEquals': {'aws:SourceAccount': ref('AWS::AccountId')},
                          'ArnLike': {'aws:SourceArn': sub('arn:${AWS::Partition}:budgets::${AWS::AccountId}:*')}}}]}}}
    subscriber = [{'SubscriptionType': 'SNS', 'Address': ref('SpendGuardTopic')}]
    notification = lambda kind, percent: {'Notification': {'NotificationType': kind, 'ComparisonOperator': 'GREATER_THAN',
        'Threshold': percent, 'ThresholdType': 'PERCENTAGE'}, 'Subscribers': subscriber}
    resources['MonthlyBudget'] = {'Type': 'AWS::Budgets::Budget', **when, 'DependsOn': 'SpendGuardTopicPolicy', 'Properties': {
        'Budget': {'BudgetName': budget_name, 'BudgetType': 'COST', 'TimeUnit': 'MONTHLY',
                   'BudgetLimit': {'Amount': ref('MonthlyBudgetUsd'), 'Unit': 'USD'}},
        'NotificationsWithSubscribers': [notification('ACTUAL', 80), notification('FORECASTED', 100),
                                         notification('ACTUAL', ref('SpendGuardThresholdPercent'))]}}
    resources['SpendGuardFunction'] = {'Type': 'AWS::Serverless::Function', **when, 'Properties': {
        'FunctionName': sub('${AWS::StackName}-spend-guard'), 'CodeUri': '../backend/',
        'Handler': 'cloudhub.spend_guard.sns_handler', 'Runtime': 'python3.13', 'Architectures': ['x86_64'],
        'Timeout': 30, 'MemorySize': 256,
        'Environment': {'Variables': {'TABLE_NAME': ref('Table'), 'ALERT_TOPIC_ARN': ref('AlertTopic'),
            'SPEND_GUARD_BUDGET_NAME': budget_name, 'SPEND_GUARD_THRESHOLD_PERCENT': ref('SpendGuardThresholdPercent')}},
        'Policies': [{'Version': '2012-10-17', 'Statement': [
            {'Effect': 'Allow', 'Action': ['dynamodb:GetItem', 'dynamodb:PutItem', 'dynamodb:ConditionCheckItem'],
             'Resource': att('Table'), 'Condition': {'ForAllValues:StringEquals': {'dynamodb:LeadingKeys': ['G#SPEND_GUARD']}}},
            {'Effect': 'Allow', 'Action': 'sns:Publish', 'Resource': ref('AlertTopic')}]}],
        'Events': {'Budget': {'Type': 'SNS', 'Properties': {'Topic': ref('SpendGuardTopic')}}}}}
    resources['SpendGuardFunctionLog'] = {'Type': 'AWS::Logs::LogGroup', **when, 'Properties': {
        'LogGroupName': sub('/aws/lambda/${AWS::StackName}-spend-guard'), 'RetentionInDays': 14}}
    resources['SpendGuardErrorAlarm'] = {'Type': 'AWS::CloudWatch::Alarm', **when, 'Properties': {
        'AlarmDescription': 'Budget notification could not be turned into a spend freeze',
        'Namespace': 'AWS/Lambda', 'MetricName': 'Errors', 'Dimensions': [{'Name': 'FunctionName', 'Value': ref('SpendGuardFunction')}],
        'Statistic': 'Sum', 'Period': 60, 'EvaluationPeriods': 1, 'Threshold': 1, 'ComparisonOperator': 'GreaterThanOrEqualToThreshold',
        'TreatMissingData': 'notBreaching', 'AlarmActions': [ref('AlertTopic')]}}


def tracing(resources):
    for name, resource in resources.items():
        props = resource.get('Properties', {})
        if resource['Type'] == 'AWS::Serverless::Function':
            props['Tracing'] = 'Active'
            props.setdefault('Policies', []).append({'Version': '2012-10-17', 'Statement': [
                {'Effect': 'Allow', 'Action': XRAY_ACTIONS, 'Resource': '*'}]})
        elif resource['Type'] == 'AWS::Serverless::StateMachine':
            props['Tracing'] = {'Enabled': True}
            props.setdefault('Policies', []).append({'Version': '2012-10-17', 'Statement': [
                {'Effect': 'Allow', 'Action': XRAY_ACTIONS, 'Resource': '*'}]})


def identity_waf(params, conditions, resources):
    params['IdentityWafEnabled'] = {'Type': 'String', 'AllowedValues': ['false', 'true'], 'Default': 'false',
        'Description': 'Attach a regional AWS WAF web ACL to the Cognito user pool (about 7 USD/month plus requests).'}
    conditions['HasIdentityWaf'] = {'Fn::Equals': [ref('IdentityWafEnabled'), 'true']}
    resources['IdentityWebAcl'] = {'Type': 'AWS::WAFv2::WebACL', 'Condition': 'HasIdentityWaf', 'Properties': {
        'Name': sub('${AWS::StackName}-identity'), 'Scope': 'REGIONAL', 'DefaultAction': {'Allow': {}},
        'Description': 'CloudHub Cognito user pool: IP reputation and per-IP rate limit',
        'Rules': [managed_rule('AWSManagedRulesAmazonIpReputationList', 0), rate_rule(IDENTITY_RATE_LIMIT, 1)],
        'VisibilityConfig': visibility('CloudHubIdentity')}}
    resources['IdentityWebAclAssociation'] = {'Type': 'AWS::WAFv2::WebACLAssociation', 'Condition': 'HasIdentityWaf',
        'Properties': {'ResourceArn': att('UserPool'), 'WebACLArn': att('IdentityWebAcl')}}


def extend(template):
    params, resources = template['Parameters'], template['Resources']
    conditions = template.setdefault('Conditions', {})
    spend_guard(params, conditions, resources)
    tracing(resources)
    identity_waf(params, conditions, resources)
    events = resources['ApiFunction']['Properties']['Events']
    for method in ('GET', 'POST'):
        events['SpendGuard' + method.title()] = {'Type': 'HttpApi', 'Properties': {
            'ApiId': ref('HttpApi'), 'Method': method, 'Path': '/admin/spend-guard'}}
    dashboard = resources.get('OperationsDashboard')
    if dashboard:
        body = json.loads(dashboard['Properties']['DashboardBody']['Fn::Sub'])
        body['widgets'].append({'type': 'metric', 'x': 0, 'y': 12, 'width': 24, 'height': 6, 'properties': {
            'title': 'Lifecycle executions (Step Functions)', 'region': '${AWS::Region}', 'period': 300, 'stat': 'Sum',
            'metrics': [['AWS/States', 'ExecutionsStarted', 'StateMachineArn', '${StateMachine}'],
                        ['.', 'ExecutionsSucceeded', '.', '.'], ['.', 'ExecutionsFailed', '.', '.'], ['.', 'ExecutionsTimedOut', '.', '.']]}})
        dashboard['Properties']['DashboardBody'] = {'Fn::Sub': json.dumps(body)}
    template.setdefault('Outputs', {})['SpendGuardTopic'] = {'Condition': 'HasSpendBudget', 'Value': ref('SpendGuardTopic')}
    return template
