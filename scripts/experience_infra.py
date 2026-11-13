"""User-experience monitoring: what a visitor actually sees, not only server metrics.

Stack ``cloudhub-user-experience`` (control Region):

* CloudWatch Synthetics canary ``cloudhub-journey``: a headless Chrome opens the
  site every 10 minutes, waits until the nine templates are rendered, then calls
  the edge-cached catalog and ``/ui-context`` like the page does. Screenshots,
  HAR files and logs go to a private bucket (30 days). An alarm fires when fewer
  than 90 % of runs succeed.
* CloudWatch RUM app monitor ``cloudhub-web``: page-load timings (including
  LCP, CLS and INP) and JavaScript errors from real browsers. Browsers send
  events with temporary credentials from a Cognito identity pool whose guest
  role may only call ``rum:PutRumEvents`` on this monitor. ``frontend/rum.js``
  starts the client when ``rum-config.json`` (output ``RumConfig``) is deployed.
"""
import json
from pathlib import Path

CANARY = 'cloudhub-journey'
CANARY_RUNTIME = 'syn-nodejs-puppeteer-9.1'
CANARY_RATE = 'rate(10 minutes)'
MONITOR = 'cloudhub-web'
TEMPLATE_COUNT = 9


def ref(name): return {'Ref': name}
def sub(text): return {'Fn::Sub': text}
def getatt(name, attr): return {'Fn::GetAtt': [name, attr]}


JOURNEY = '''const synthetics = require('Synthetics');
const log = require('SyntheticsLogger');
const SITE = process.env.SITE_URL;
const TEMPLATES = Number(process.env.TEMPLATE_COUNT);

async function json(page, path) {
  return page.evaluate(async path => {
    const r = await fetch(path, {cache: 'no-store', credentials: 'omit'});
    const body = r.ok ? await r.json() : null;
    return {status: r.status, cache: r.headers.get('x-cache'), pop: r.headers.get('x-amz-cf-pop'),
            snapshot: r.headers.get('x-amz-meta-snapshot-at'), items: body && Array.isArray(body.items) ? body.items.length : null,
            country: body ? body.country_code || null : null};
  }, path);
}

exports.handler = async function () {
  const page = await synthetics.getPage();
  await synthetics.executeStep('open-home', async function () {
    const response = await page.goto(SITE, {waitUntil: 'domcontentloaded', timeout: 30000});
    if (!response || response.status() !== 200) throw new Error('home page status ' + (response && response.status()));
  });
  await synthetics.executeStep('templates-rendered', async function () {
    await page.waitForFunction(n => document.querySelectorAll('#catalog > *').length >= n, {timeout: 20000}, TEMPLATES);
  });
  await synthetics.executeStep('edge-catalog', async function () {
    const r = await json(page, '/public/catalog');
    log.info('edge catalog ' + JSON.stringify(r));
    if (r.status !== 200 || r.items < TEMPLATES) throw new Error('edge catalog ' + JSON.stringify(r));
  });
  await synthetics.executeStep('ui-context', async function () {
    const r = await json(page, '/ui-context');
    log.info('ui-context ' + JSON.stringify(r));
    if (r.status !== 200) throw new Error('ui-context ' + JSON.stringify(r));
  });
};
'''


def regional():
    monitor_arn = sub('arn:${AWS::Partition}:rum:${AWS::Region}:${AWS::AccountId}:appmonitor/' + MONITOR)
    return {'AWSTemplateFormatVersion': '2010-09-09',
        'Description': 'CloudHub user-experience monitoring: Synthetics journey canary and CloudWatch RUM',
        'Parameters': {
            'FrontendDomain': {'Type': 'String', 'Default': 'cloudhub1.me'},
            'AlertTopicArn': {'Type': 'String', 'Description': 'Existing AlertTopic of the control-plane stack'}},
        'Resources': {
            'CanaryArtifacts': {'Type': 'AWS::S3::Bucket', 'Properties': {
                'BucketEncryption': {'ServerSideEncryptionConfiguration': [{'ServerSideEncryptionByDefault': {'SSEAlgorithm': 'AES256'}}]},
                'PublicAccessBlockConfiguration': {'BlockPublicAcls': True, 'BlockPublicPolicy': True, 'IgnorePublicAcls': True, 'RestrictPublicBuckets': True},
                'OwnershipControls': {'Rules': [{'ObjectOwnership': 'BucketOwnerEnforced'}]},
                'LifecycleConfiguration': {'Rules': [{'Id': 'expire-artifacts', 'Status': 'Enabled', 'ExpirationInDays': 30}]}}},
            'CanaryRole': {'Type': 'AWS::IAM::Role', 'Properties': {
                'AssumeRolePolicyDocument': {'Version': '2012-10-17', 'Statement': [{'Effect': 'Allow',
                    'Principal': {'Service': 'lambda.amazonaws.com'}, 'Action': 'sts:AssumeRole'}]},
                'Policies': [{'PolicyName': 'synthetics-canary', 'PolicyDocument': {'Version': '2012-10-17', 'Statement': [
                    {'Effect': 'Allow', 'Action': ['s3:PutObject', 's3:GetObject'], 'Resource': sub('${CanaryArtifacts.Arn}/*')},
                    {'Effect': 'Allow', 'Action': 's3:GetBucketLocation', 'Resource': getatt('CanaryArtifacts', 'Arn')},
                    {'Effect': 'Allow', 'Action': 's3:ListAllMyBuckets', 'Resource': '*'},
                    {'Effect': 'Allow', 'Action': ['logs:CreateLogGroup', 'logs:CreateLogStream', 'logs:PutLogEvents'],
                     'Resource': sub('arn:${AWS::Partition}:logs:${AWS::Region}:${AWS::AccountId}:log-group:/aws/lambda/cwsyn-*')},
                    {'Effect': 'Allow', 'Action': 'cloudwatch:PutMetricData', 'Resource': '*',
                     'Condition': {'StringEquals': {'cloudwatch:namespace': 'CloudWatchSynthetics'}}}]}}]}},
            'JourneyCanary': {'Type': 'AWS::Synthetics::Canary', 'Properties': {
                'Name': CANARY, 'RuntimeVersion': CANARY_RUNTIME, 'ExecutionRoleArn': getatt('CanaryRole', 'Arn'),
                'ArtifactS3Location': sub('s3://${CanaryArtifacts}/journey'),
                'ArtifactConfig': {'S3Encryption': {'EncryptionMode': 'SSE_S3'}},
                'Code': {'Handler': 'journey.handler', 'Script': JOURNEY},
                'Schedule': {'Expression': CANARY_RATE},
                'RunConfig': {'TimeoutInSeconds': 90, 'MemoryInMB': 1024,
                              'EnvironmentVariables': {'SITE_URL': sub('https://${FrontendDomain}/'), 'TEMPLATE_COUNT': str(TEMPLATE_COUNT)}},
                'SuccessRetentionPeriod': 7, 'FailureRetentionPeriod': 30, 'StartCanaryAfterCreation': True}},
            'JourneyAlarm': {'Type': 'AWS::CloudWatch::Alarm', 'Properties': {
                'AlarmName': sub('${AWS::StackName}-journey-failing'),
                'AlarmDescription': 'Synthetic user journey succeeds in fewer than 90 % of runs (2 of 3 twenty-minute windows)',
                'Namespace': 'CloudWatchSynthetics', 'MetricName': 'SuccessPercent',
                'Dimensions': [{'Name': 'CanaryName', 'Value': ref('JourneyCanary')}],
                'Statistic': 'Average', 'Period': 1200, 'EvaluationPeriods': 3, 'DatapointsToAlarm': 2,
                'Threshold': 90, 'ComparisonOperator': 'LessThanThreshold', 'TreatMissingData': 'notBreaching',
                'AlarmActions': [ref('AlertTopicArn')], 'OKActions': [ref('AlertTopicArn')]}},
            'RumIdentityPool': {'Type': 'AWS::Cognito::IdentityPool', 'Properties': {
                'IdentityPoolName': 'cloudhub_rum', 'AllowUnauthenticatedIdentities': True, 'AllowClassicFlow': True}},
            'RumGuestRole': {'Type': 'AWS::IAM::Role', 'Properties': {
                'Description': 'Anonymous browsers may only send RUM events to the CloudHub app monitor',
                'MaxSessionDuration': 3600,
                'AssumeRolePolicyDocument': {'Version': '2012-10-17', 'Statement': [{'Effect': 'Allow',
                    'Principal': {'Federated': 'cognito-identity.amazonaws.com'}, 'Action': 'sts:AssumeRoleWithWebIdentity',
                    'Condition': {'StringEquals': {'cognito-identity.amazonaws.com:aud': ref('RumIdentityPool')},
                                  'ForAnyValue:StringLike': {'cognito-identity.amazonaws.com:amr': 'unauthenticated'}}}]},
                'Policies': [{'PolicyName': 'put-rum-events', 'PolicyDocument': {'Version': '2012-10-17', 'Statement': [
                    {'Effect': 'Allow', 'Action': 'rum:PutRumEvents', 'Resource': monitor_arn}]}}]}},
            'RumRoles': {'Type': 'AWS::Cognito::IdentityPoolRoleAttachment', 'Properties': {
                'IdentityPoolId': ref('RumIdentityPool'), 'Roles': {'unauthenticated': getatt('RumGuestRole', 'Arn')}}},
            'RumMonitor': {'Type': 'AWS::RUM::AppMonitor', 'Properties': {
                'Name': MONITOR, 'Domain': ref('FrontendDomain'), 'CwLogEnabled': False,
                'AppMonitorConfiguration': {'AllowCookies': False, 'EnableXRay': False, 'SessionSampleRate': 1,
                    'Telemetries': ['performance', 'errors'],
                    'IdentityPoolId': ref('RumIdentityPool'), 'GuestRoleArn': getatt('RumGuestRole', 'Arn')}}}},
        'Outputs': {
            'CanaryName': {'Value': ref('JourneyCanary')},
            'ArtifactBucket': {'Value': ref('CanaryArtifacts')},
            'RumConfig': {'Description': 'Contents of rum-config.json next to index.html',
                'Value': sub(json.dumps({'appMonitorId': '${RumMonitor.Id}', 'identityPoolId': '${RumIdentityPool}',
                                         'guestRoleArn': '${RumGuestRole.Arn}', 'region': '${AWS::Region}', 'sessionSampleRate': 1},
                                        separators=(',', ':')))}}}


if __name__ == '__main__':
    out = Path(__file__).resolve().parents[1] / 'infra/experience'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'regional.json').write_text(json.dumps(regional(), indent=2) + '\n', encoding='utf-8')
    print('Generated', out)
