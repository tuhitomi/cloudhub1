"""Account security baseline (CIS AWS Foundations style), separate from CloudHub stacks.

* Multi-Region CloudTrail with log-file validation into a locked-down S3 bucket
  (SSE-S3, TLS only, no public access, object ownership enforced, 1-year expiry).
* Trail events also flow to CloudWatch Logs (90-day retention) so metric
  filters can alarm in near real time on: root account use, console sign-in
  without MFA, unauthorized API calls, IAM policy changes and CloudTrail
  configuration changes (CIS 4.1/4.2/4.3/4.4/4.5).
* IAM Access Analyzer (account zone of trust) reports resources shared outside
  the account, for example a public S3 bucket or a role trusting another account.

GuardDuty and Security Hub are not part of this stack: they need the account to
finish AWS verification first (SubscriptionRequiredException at enable time).
"""
import json
from pathlib import Path


def ref(name): return {'Ref': name}
def sub(text): return {'Fn::Sub': text}
def att(name, key='Arn'): return {'Fn::GetAtt': [name, key]}


FILTERS = [
    ('RootUsage', 'Root account was used', '{ $.userIdentity.type = "Root" && $.userIdentity.invokedBy NOT EXISTS && $.eventType != "AwsServiceEvent" }'),
    ('ConsoleNoMfa', 'Console sign-in without MFA', '{ ($.eventName = "ConsoleLogin") && ($.additionalEventData.MFAUsed != "Yes") && ($.userIdentity.type = "IAMUser") && ($.responseElements.ConsoleLogin = "Success") }'),
    ('UnauthorizedCalls', 'Unauthorized or access-denied API calls', '{ ($.errorCode = "*UnauthorizedOperation") || ($.errorCode = "AccessDenied*") }'),
    ('IamPolicyChanges', 'IAM policy changed', '{ ($.eventSource = "iam.amazonaws.com") && (($.eventName = "DeleteGroupPolicy") || ($.eventName = "DeleteRolePolicy") || ($.eventName = "DeleteUserPolicy") || ($.eventName = "PutGroupPolicy") || ($.eventName = "PutRolePolicy") || ($.eventName = "PutUserPolicy") || ($.eventName = "CreatePolicy") || ($.eventName = "DeletePolicy") || ($.eventName = "CreatePolicyVersion") || ($.eventName = "DeletePolicyVersion") || ($.eventName = "AttachRolePolicy") || ($.eventName = "DetachRolePolicy") || ($.eventName = "AttachUserPolicy") || ($.eventName = "DetachUserPolicy") || ($.eventName = "AttachGroupPolicy") || ($.eventName = "DetachGroupPolicy")) }'),
    ('TrailChanges', 'CloudTrail configuration changed', '{ ($.eventName = "CreateTrail") || ($.eventName = "UpdateTrail") || ($.eventName = "DeleteTrail") || ($.eventName = "StartLogging") || ($.eventName = "StopLogging") }'),
]
# Unauthorized calls happen in small numbers during normal console browsing.
THRESHOLDS = {'UnauthorizedCalls': 10}


def template():
    r = {
        'TrailBucket': {'Type': 'AWS::S3::Bucket', 'DeletionPolicy': 'Retain', 'UpdateReplacePolicy': 'Retain', 'Properties': {
            'BucketEncryption': {'ServerSideEncryptionConfiguration': [{'ServerSideEncryptionByDefault': {'SSEAlgorithm': 'AES256'}}]},
            'PublicAccessBlockConfiguration': {k: True for k in ('BlockPublicAcls', 'BlockPublicPolicy', 'IgnorePublicAcls', 'RestrictPublicBuckets')},
            'OwnershipControls': {'Rules': [{'ObjectOwnership': 'BucketOwnerEnforced'}]},
            'VersioningConfiguration': {'Status': 'Enabled'},
            'LifecycleConfiguration': {'Rules': [{'Id': 'expire-after-1-year', 'Status': 'Enabled', 'ExpirationInDays': 365,
                                                  'NoncurrentVersionExpiration': {'NoncurrentDays': 30}}]}}},
        'TrailBucketPolicy': {'Type': 'AWS::S3::BucketPolicy', 'Properties': {'Bucket': ref('TrailBucket'), 'PolicyDocument': {
            'Version': '2012-10-17', 'Statement': [
                {'Sid': 'AclCheck', 'Effect': 'Allow', 'Principal': {'Service': 'cloudtrail.amazonaws.com'}, 'Action': 's3:GetBucketAcl',
                 'Resource': att('TrailBucket'), 'Condition': {'StringEquals': {'aws:SourceArn': sub('arn:${AWS::Partition}:cloudtrail:${AWS::Region}:${AWS::AccountId}:trail/${AWS::StackName}')}}},
                {'Sid': 'Write', 'Effect': 'Allow', 'Principal': {'Service': 'cloudtrail.amazonaws.com'}, 'Action': 's3:PutObject',
                 'Resource': sub('${TrailBucket.Arn}/AWSLogs/${AWS::AccountId}/*'),
                 'Condition': {'StringEquals': {'s3:x-amz-acl': 'bucket-owner-full-control',
                                                'aws:SourceArn': sub('arn:${AWS::Partition}:cloudtrail:${AWS::Region}:${AWS::AccountId}:trail/${AWS::StackName}')}}},
                {'Sid': 'TlsOnly', 'Effect': 'Deny', 'Principal': '*', 'Action': 's3:*', 'Resource': [att('TrailBucket'), sub('${TrailBucket.Arn}/*')],
                 'Condition': {'Bool': {'aws:SecureTransport': 'false'}}}]}}},
        'TrailLogGroup': {'Type': 'AWS::Logs::LogGroup', 'Properties': {'LogGroupName': sub('/aws/cloudtrail/${AWS::StackName}'), 'RetentionInDays': 90}},
        'TrailLogRole': {'Type': 'AWS::IAM::Role', 'Properties': {
            'AssumeRolePolicyDocument': {'Version': '2012-10-17', 'Statement': [{'Effect': 'Allow', 'Principal': {'Service': 'cloudtrail.amazonaws.com'}, 'Action': 'sts:AssumeRole'}]},
            'Policies': [{'PolicyName': 'deliver', 'PolicyDocument': {'Version': '2012-10-17', 'Statement': [{'Effect': 'Allow',
                'Action': ['logs:CreateLogStream', 'logs:PutLogEvents'], 'Resource': sub('${TrailLogGroup.Arn}')}]}}]}},
        'Trail': {'Type': 'AWS::CloudTrail::Trail', 'DependsOn': 'TrailBucketPolicy', 'Properties': {
            'TrailName': sub('${AWS::StackName}'), 'S3BucketName': ref('TrailBucket'), 'IsLogging': True, 'IsMultiRegionTrail': True,
            'IncludeGlobalServiceEvents': True, 'EnableLogFileValidation': True,
            'CloudWatchLogsLogGroupArn': att('TrailLogGroup'), 'CloudWatchLogsRoleArn': att('TrailLogRole')}},
        'AccessAnalyzer': {'Type': 'AWS::AccessAnalyzer::Analyzer', 'Properties': {'AnalyzerName': sub('${AWS::StackName}-account'), 'Type': 'ACCOUNT'}},
    }
    for name, description, pattern in FILTERS:
        r[name + 'Filter'] = {'Type': 'AWS::Logs::MetricFilter', 'DependsOn': 'Trail', 'Properties': {
            'LogGroupName': ref('TrailLogGroup'), 'FilterPattern': pattern,
            'MetricTransformations': [{'MetricNamespace': 'CloudHub/Security', 'MetricName': name, 'MetricValue': '1', 'DefaultValue': 0}]}}
        r[name + 'Alarm'] = {'Type': 'AWS::CloudWatch::Alarm', 'Properties': {
            'AlarmName': sub('${AWS::StackName}-' + name), 'AlarmDescription': description,
            'Namespace': 'CloudHub/Security', 'MetricName': name, 'Statistic': 'Sum', 'Period': 300, 'EvaluationPeriods': 1,
            'Threshold': THRESHOLDS.get(name, 1), 'ComparisonOperator': 'GreaterThanOrEqualToThreshold',
            'TreatMissingData': 'notBreaching', 'AlarmActions': [ref('AlertTopicArn')]}}
    return {'AWSTemplateFormatVersion': '2010-09-09',
            'Description': 'CloudHub account security baseline: CloudTrail, CIS metric alarms, IAM Access Analyzer',
            'Parameters': {'AlertTopicArn': {'Type': 'String', 'AllowedPattern': 'arn:aws:sns:[a-z0-9-]+:[0-9]{12}:.+'}},
            'Resources': r,
            'Outputs': {'TrailBucket': {'Value': ref('TrailBucket')}, 'Analyzer': {'Value': att('AccessAnalyzer')}}}


if __name__ == '__main__':
    out = Path(__file__).resolve().parents[1] / 'infra/security/baseline.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(template(), indent=2) + '\n', encoding='utf-8')
    print('Generated', out)
