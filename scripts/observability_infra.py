"""Production observability for an already running CloudHub control plane.

Two standalone stacks; neither modifies the control-plane stack:

* ``regional()`` (control Region): SLO dashboard, multi-window error-budget burn
  alarms for the HTTP API, Lambda throttle/concurrency, DynamoDB and Step
  Functions alarms. Notifications go to the existing AlertTopic.
* ``global_checks()`` (us-east-1, where Route 53 health-check and CloudFront
  metrics live): HTTPS health checks of the website and API from several AWS
  Regions, a CloudFront 5xx alarm and an SNS topic for them.

SLO: 99.5 % of API requests answered without a 5xx over 30 days, so the error
budget is 0.5 %. Burn-rate alarms follow the multi-window method from the
Google SRE workbook: page when the 1 h burn rate exceeds 14.4 (2 % of the
monthly budget in an hour) or the 6 h burn rate exceeds 6 (5 % in six hours).
"""
import json
from pathlib import Path

SLO_TARGET = 0.995
BUDGET = round(1 - SLO_TARGET, 6)
FAST_BURN, SLOW_BURN = 14.4, 6.0
LAMBDA_ROLES = ('api', 'worker', 'sweep', 'expiry')
CHECK_REGIONS = ['ap-southeast-1', 'ap-northeast-1', 'us-east-1', 'eu-west-1']


def ref(name): return {'Ref': name}
def sub(text): return {'Fn::Sub': text}


def metric(namespace, name, dims, stat, period=60, label=None, **extra):
    m = [namespace, name]
    for k, v in dims.items():
        m += [k, v]
    opts = {'stat': stat, 'period': period, **extra}
    if label:
        opts['label'] = label
    return m + [opts]


def burn_alarm(name, window, threshold, api):
    q = lambda mid, metric_name: {'Id': mid, 'ReturnData': False, 'MetricStat': {
        'Metric': {'Namespace': 'AWS/ApiGateway', 'MetricName': metric_name, 'Dimensions': [{'Name': 'ApiId', 'Value': api}]},
        'Period': window, 'Stat': 'Sum'}}
    return {'Type': 'AWS::CloudWatch::Alarm', 'Properties': {
        'AlarmName': sub('${AWS::StackName}-' + name),
        'AlarmDescription': f'Error-budget burn rate over {window // 3600} h above {threshold} (SLO {SLO_TARGET:.1%} non-5xx)',
        'Metrics': [q('errors', '5xx'), q('requests', 'Count'),
                    {'Id': 'burn', 'ReturnData': True, 'Label': 'burn rate',
                     'Expression': f'IF(requests > 0, (errors / requests) / {BUDGET}, 0)'}],
        'EvaluationPeriods': 1, 'Threshold': threshold, 'ComparisonOperator': 'GreaterThanThreshold',
        'TreatMissingData': 'notBreaching', 'AlarmActions': [ref('AlertTopicArn')], 'OKActions': [ref('AlertTopicArn')]}}


def simple_alarm(description, namespace, name, dims, stat, threshold, period=300, evaluations=1, op='GreaterThanThreshold', datapoints=None):
    props = {'AlarmName': sub('${AWS::StackName}-' + name.replace(' ', '')), 'AlarmDescription': description,
             'Namespace': namespace, 'MetricName': name.split(':')[0],
             'Dimensions': [{'Name': k, 'Value': v} for k, v in dims.items()], 'Period': period,
             'EvaluationPeriods': evaluations, 'Threshold': threshold, 'ComparisonOperator': op,
             'TreatMissingData': 'notBreaching', 'AlarmActions': [ref('AlertTopicArn')]}
    props['ExtendedStatistic' if stat.startswith('p') else 'Statistic'] = stat
    if datapoints:
        props['DatapointsToAlarm'] = datapoints
    return {'Type': 'AWS::CloudWatch::Alarm', 'Properties': props}


def regional():
    api, stack, table = '${ApiId}', '${ControlStack}', '${TableName}'
    fn = lambda role: '${ControlStack}-' + role
    machine = 'arn:aws:states:${AWS::Region}:${AWS::AccountId}:stateMachine:${ControlStack}-lifecycle'
    w = lambda x, y, wd, h, props: {'type': 'metric', 'x': x, 'y': y, 'width': wd, 'height': h, 'properties': {'region': '${AWS::Region}', **props}}
    text = lambda x, y, wd, h, md: {'type': 'text', 'x': x, 'y': y, 'width': wd, 'height': h, 'properties': {'markdown': md}}
    widgets = [
        text(0, 0, 24, 2, f'# CloudHub production · SLO {SLO_TARGET:.1%} non-5xx (30 ngày) · error budget {BUDGET:.1%}\n'
                          f'Burn-rate alarms: 1 h > {FAST_BURN} hoặc 6 h > {SLOW_BURN}. Tài khoản Lambda concurrency được theo dõi vì giới hạn tài khoản mới rất thấp.'),
        w(0, 2, 8, 6, {'title': 'Availability (non-5xx, %)', 'view': 'singleValue', 'period': 2592000, 'metrics': [
            metric('AWS/ApiGateway', 'Count', {'ApiId': api}, 'Sum', 2592000, id='c', visible=False),
            metric('AWS/ApiGateway', '5xx', {'ApiId': api}, 'Sum', 2592000, id='e', visible=False),
            [{'expression': 'IF(c > 0, 100 * (1 - e / c), 100)', 'label': '30-day availability', 'id': 'a'}],
            [{'expression': f'IF(c > 0, 100 * (1 - (e / c) / {BUDGET}), 100)', 'label': 'error budget left %', 'id': 'b'}]]}),
        w(8, 2, 16, 6, {'title': 'API requests and errors', 'view': 'timeSeries', 'stacked': False, 'metrics': [
            metric('AWS/ApiGateway', 'Count', {'ApiId': api}, 'Sum', label='requests'),
            metric('AWS/ApiGateway', '4xx', {'ApiId': api}, 'Sum', label='4xx (gồm 429 throttle)'),
            metric('AWS/ApiGateway', '5xx', {'ApiId': api}, 'Sum', label='5xx')]}),
        w(0, 8, 12, 6, {'title': 'API latency (ms)', 'view': 'timeSeries', 'metrics': [
            metric('AWS/ApiGateway', 'Latency', {'ApiId': api}, 'p50', label='p50'),
            metric('AWS/ApiGateway', 'Latency', {'ApiId': api}, 'p95', label='p95'),
            metric('AWS/ApiGateway', 'Latency', {'ApiId': api}, 'p99', label='p99'),
            metric('AWS/ApiGateway', 'IntegrationLatency', {'ApiId': api}, 'p95', label='integration p95')],
            'annotations': {'horizontal': [{'value': 2000, 'label': 'mục tiêu 2 s'}]}}),
        w(12, 8, 12, 6, {'title': 'Lambda concurrency vs account quota', 'view': 'timeSeries', 'metrics': [
            metric('AWS/Lambda', 'ClaimedAccountConcurrency', {}, 'Maximum', label='claimed (account)'),
            metric('AWS/Lambda', 'ConcurrentExecutions', {}, 'Maximum', label='concurrent (account)'),
            metric('AWS/Lambda', 'Throttles', {}, 'Sum', label='throttles (account)', yAxis='right')]}),
        w(0, 14, 12, 6, {'title': 'Lambda duration p95 (ms)', 'view': 'timeSeries', 'metrics': [
            metric('AWS/Lambda', 'Duration', {'FunctionName': fn(r)}, 'p95', label=r) for r in LAMBDA_ROLES]}),
        w(12, 14, 12, 6, {'title': 'Lambda errors', 'view': 'timeSeries', 'metrics': [
            metric('AWS/Lambda', 'Errors', {'FunctionName': fn(r)}, 'Sum', label=r) for r in LAMBDA_ROLES]}),
        w(0, 20, 12, 6, {'title': 'DynamoDB metadata table', 'view': 'timeSeries', 'metrics': [
            metric('AWS/DynamoDB', 'ConsumedReadCapacityUnits', {'TableName': table}, 'Sum', label='RCU'),
            metric('AWS/DynamoDB', 'ConsumedWriteCapacityUnits', {'TableName': table}, 'Sum', label='WCU'),
            metric('AWS/DynamoDB', 'ThrottledRequests', {'TableName': table}, 'Sum', label='throttled', yAxis='right')]}),
        w(12, 20, 12, 6, {'title': 'Lifecycle workflow (Step Functions)', 'view': 'timeSeries', 'period': 300, 'metrics': [
            metric('AWS/States', 'ExecutionsStarted', {'StateMachineArn': machine}, 'Sum', 300, label='started'),
            metric('AWS/States', 'ExecutionsSucceeded', {'StateMachineArn': machine}, 'Sum', 300, label='succeeded'),
            metric('AWS/States', 'ExecutionsFailed', {'StateMachineArn': machine}, 'Sum', 300, label='failed'),
            metric('AWS/States', 'ExecutionTime', {'StateMachineArn': machine}, 'p95', 300, label='time p95 (ms)', yAxis='right')]}),
        w(0, 26, 24, 6, {'title': 'CloudFront cloudhub1.me (us-east-1, Global)', 'region': 'us-east-1', 'view': 'timeSeries', 'metrics': [
            metric('AWS/CloudFront', 'Requests', {'DistributionId': '${DistributionId}', 'Region': 'Global'}, 'Sum', label='requests'),
            metric('AWS/CloudFront', '4xxErrorRate', {'DistributionId': '${DistributionId}', 'Region': 'Global'}, 'Average', label='4xx %', yAxis='right'),
            metric('AWS/CloudFront', '5xxErrorRate', {'DistributionId': '${DistributionId}', 'Region': 'Global'}, 'Average', label='5xx %', yAxis='right')]}),
    ]
    params = {
        'ControlStack': {'Type': 'String', 'Default': 'cloudhub-pages-live'},
        'ApiId': {'Type': 'String', 'AllowedPattern': '[a-z0-9]{10}'},
        'TableName': {'Type': 'String'},
        'DistributionId': {'Type': 'String', 'AllowedPattern': 'E[A-Z0-9]+'},
        'AlertTopicArn': {'Type': 'String', 'AllowedPattern': 'arn:aws:sns:[a-z0-9-]+:[0-9]{12}:.+'},
        'AccountConcurrencyLimit': {'Type': 'Number', 'Default': 10, 'MinValue': 10,
            'Description': 'Current Lambda concurrent-executions quota; the alarm fires at 80 %.'},
    }
    r = {
        'SloDashboard': {'Type': 'AWS::CloudWatch::Dashboard', 'Properties': {
            'DashboardName': sub('${AWS::StackName}-slo'), 'DashboardBody': sub(json.dumps({'widgets': widgets}))}},
        'ApiFastBurnAlarm': burn_alarm('api-burn-1h', 3600, FAST_BURN, sub(api)),
        'ApiSlowBurnAlarm': burn_alarm('api-burn-6h', 21600, SLOW_BURN, sub(api)),
        'ApiLatencyAlarm': simple_alarm('HTTP API p95 latency above 2 s in 3 of 5 minutes', 'AWS/ApiGateway', 'Latency',
                                        {'ApiId': sub(api)}, 'p95', 2000, 60, 5, datapoints=3),
        'LambdaThrottleAlarm': simple_alarm('Any Lambda invocation in the account was throttled', 'AWS/Lambda', 'Throttles', {}, 'Sum', 0, 60),
        'DynamoThrottleAlarm': simple_alarm('DynamoDB metadata table throttled requests', 'AWS/DynamoDB', 'ThrottledRequests',
                                            {'TableName': sub(table)}, 'Sum', 0, 60),
        'WorkflowFailureAlarm': simple_alarm('Lifecycle Step Functions execution failed or timed out', 'AWS/States', 'ExecutionsFailed',
                                             {'StateMachineArn': sub(machine)}, 'Sum', 0, 300),
        'ConcurrencyAlarm': {'Type': 'AWS::CloudWatch::Alarm', 'Properties': {
            'AlarmName': sub('${AWS::StackName}-account-concurrency-80pct'),
            'AlarmDescription': 'Claimed Lambda concurrency above 80 % of the account quota',
            'Metrics': [{'Id': 'claimed', 'ReturnData': False, 'MetricStat': {'Metric': {'Namespace': 'AWS/Lambda', 'MetricName': 'ClaimedAccountConcurrency'},
                                                                              'Period': 60, 'Stat': 'Maximum'}},
                        {'Id': 'ratio', 'ReturnData': True, 'Label': 'quota used', 'Expression': sub('claimed / ${AccountConcurrencyLimit}')}],
            'EvaluationPeriods': 3, 'DatapointsToAlarm': 2, 'Threshold': 0.8, 'ComparisonOperator': 'GreaterThanThreshold',
            'TreatMissingData': 'notBreaching', 'AlarmActions': [ref('AlertTopicArn')]}},
    }
    r['SloPage'] = {'Type': 'AWS::CloudWatch::CompositeAlarm', 'Properties': {
        'AlarmName': sub('${AWS::StackName}-slo-page'),
        'AlarmDescription': 'Page: fast or slow error-budget burn, or account concurrency exhausted',
        'AlarmRule': sub('ALARM("${ApiFastBurnAlarm}") OR ALARM("${ApiSlowBurnAlarm}") OR ALARM("${ConcurrencyAlarm}")'),
        'AlarmActions': [ref('AlertTopicArn')]}}
    return {'AWSTemplateFormatVersion': '2010-09-09',
            'Description': 'CloudHub production SLO dashboard and alarms (does not modify the control plane)',
            'Parameters': params, 'Resources': r,
            'Outputs': {'Dashboard': {'Value': sub('https://${AWS::Region}.console.aws.amazon.com/cloudwatch/home#dashboards/dashboard/${AWS::StackName}-slo')}}}


def global_checks():
    def check(name, domain, path):
        return {'Type': 'AWS::Route53::HealthCheck', 'Properties': {
            'HealthCheckConfig': {'Type': 'HTTPS', 'FullyQualifiedDomainName': domain, 'ResourcePath': path, 'Port': 443,
                                  'RequestInterval': 30, 'FailureThreshold': 3, 'EnableSNI': True, 'Regions': CHECK_REGIONS},
            'HealthCheckTags': [{'Key': 'Name', 'Value': name}, {'Key': 'Project', 'Value': 'CloudHub'}]}}

    def down(name, check_id):
        return {'Type': 'AWS::CloudWatch::Alarm', 'Properties': {
            'AlarmName': sub('${AWS::StackName}-' + name + '-down'), 'AlarmDescription': name + ' failed health checks from several Regions',
            'Namespace': 'AWS/Route53', 'MetricName': 'HealthCheckStatus', 'Dimensions': [{'Name': 'HealthCheckId', 'Value': ref(check_id)}],
            'Statistic': 'Minimum', 'Period': 60, 'EvaluationPeriods': 3, 'DatapointsToAlarm': 2, 'Threshold': 1,
            'ComparisonOperator': 'LessThanThreshold', 'TreatMissingData': 'breaching',
            'AlarmActions': [ref('GlobalAlerts')], 'OKActions': [ref('GlobalAlerts')]}}
    return {'AWSTemplateFormatVersion': '2010-09-09',
        'Description': 'CloudHub external health checks and CloudFront alarms (us-east-1)',
        'Rules': {'UsEast1': {'Assertions': [{'Assert': {'Fn::Equals': [ref('AWS::Region'), 'us-east-1']},
                                              'AssertDescription': 'Route 53 health-check and CloudFront metrics are in us-east-1'}]}},
        'Parameters': {'FrontendDomain': {'Type': 'String', 'Default': 'cloudhub1.me'},
                       'ApiDomain': {'Type': 'String', 'Default': 'api.cloudhub1.me'},
                       'DistributionId': {'Type': 'String', 'AllowedPattern': 'E[A-Z0-9]+'},
                       'AlertEmail': {'Type': 'String', 'NoEcho': True, 'Description': 'Receives the SNS confirmation and alerts'}},
        'Resources': {
            'GlobalAlerts': {'Type': 'AWS::SNS::Topic', 'Properties': {'Subscription': [{'Protocol': 'email', 'Endpoint': ref('AlertEmail')}]}},
            'FrontendCheck': check('cloudhub-frontend', ref('FrontendDomain'), '/'),
            'ApiCheck': check('cloudhub-api', ref('ApiDomain'), '/ui-context'),
            'FrontendDownAlarm': down('frontend', 'FrontendCheck'),
            'ApiDownAlarm': down('api', 'ApiCheck'),
            'CloudFront5xxAlarm': {'Type': 'AWS::CloudWatch::Alarm', 'Properties': {
                'AlarmName': sub('${AWS::StackName}-cloudfront-5xx'), 'AlarmDescription': 'CloudFront 5xx error rate above 1 % for 5 minutes',
                'Namespace': 'AWS/CloudFront', 'MetricName': '5xxErrorRate',
                'Dimensions': [{'Name': 'DistributionId', 'Value': ref('DistributionId')}, {'Name': 'Region', 'Value': 'Global'}],
                'Statistic': 'Average', 'Period': 300, 'EvaluationPeriods': 1, 'Threshold': 1, 'ComparisonOperator': 'GreaterThanThreshold',
                'TreatMissingData': 'notBreaching', 'AlarmActions': [ref('GlobalAlerts')]}}},
        'Outputs': {'FrontendCheckId': {'Value': ref('FrontendCheck')}, 'ApiCheckId': {'Value': ref('ApiCheck')}}}


if __name__ == '__main__':
    out = Path(__file__).resolve().parents[1] / 'infra/observability'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'regional.json').write_text(json.dumps(regional(), indent=2) + '\n', encoding='utf-8')
    (out / 'global-checks.json').write_text(json.dumps(global_checks(), indent=2) + '\n', encoding='utf-8')
    print('Generated', out)
