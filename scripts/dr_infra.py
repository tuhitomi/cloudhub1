"""Multi-Region disaster recovery for the CloudHub frontend and public catalog.

Primary Region: ap-southeast-1 (Singapore). Recovery Region: ap-northeast-1 (Tokyo).

* ``tokyo()``: stack ``cloudhub-dr-tokyo`` in the recovery Region. A private,
  versioned bucket that receives the frontend by S3 Cross-Region Replication,
  plus a Lambda that stores a snapshot of ``GET /public/catalog`` there every
  15 minutes (EventBridge Scheduler).
* ``attach_failover(template)``: CloudFront origin groups on the frontend
  distribution. Static files fail over from the Singapore bucket to Tokyo on
  403/404/5xx; ``/public/catalog`` fails over from the API to the Tokyo snapshot
  on 5xx. Guests can still open the site and browse the catalog while the
  primary Region or the API is down; signing in and creating environments
  still need the primary control plane (Cognito and the API are regional).
* Data: the metadata table becomes a DynamoDB global table with a Tokyo
  replica (``replica_commands``); RPO is the replication lag, typically under
  a second, instead of the ~5 minutes of point-in-time recovery.
"""
import json
from pathlib import Path

PRIMARY, RECOVERY = 'ap-southeast-1', 'ap-northeast-1'
DR_ORIGIN = 'dr-s3'
FRONTEND_GROUP, CATALOG_GROUP = 'frontend-failover', 'catalog-failover'
FRONTEND_FAILOVER_CODES = [403, 404, 500, 502, 503, 504]
API_FAILOVER_CODES = [500, 502, 503, 504]
SNAPSHOT_KEY = 'public/catalog'
SNAPSHOT_RATE = 'rate(15 minutes)'
BUCKET_NAME = 'cloudhub-dr-frontend-${AWS::AccountId}-${AWS::Region}'


def bucket_domain(account):
    return BUCKET_NAME.replace('${AWS::AccountId}', account).replace('${AWS::Region}', RECOVERY) + f'.s3.{RECOVERY}.amazonaws.com'


def ref(name): return {'Ref': name}
def sub(text): return {'Fn::Sub': text}
def getatt(name, attr): return {'Fn::GetAtt': [name, attr]}


SNAPSHOT_CODE = '''import json, os, time, urllib.request
import boto3
s3 = boto3.client('s3')


def handler(event, context):
    request = urllib.request.Request(os.environ['CATALOG_URL'], headers={
        'Accept': 'application/json', 'User-Agent': 'CloudHub-DR-Snapshot/1'})
    with urllib.request.urlopen(request, timeout=10) as response:
        if response.status != 200:
            raise RuntimeError(f'catalog returned {response.status}')
        body = response.read()
    data = json.loads(body)
    # Keep the last good snapshot if the API answers with something unexpected.
    if not isinstance(data.get('items'), list) or not data['items'] or 'signup_policy' not in data:
        raise ValueError('unexpected catalog shape')
    at = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    s3.put_object(Bucket=os.environ['BUCKET'], Key=os.environ['KEY'], Body=body,
                  ContentType='application/json', CacheControl='public, max-age=60',
                  Metadata={'snapshot-at': at, 'source': 'cloudhub-dr-snapshot'})
    return {'items': len(data['items']), 'bytes': len(body), 'snapshot_at': at}
'''


def tokyo():
    bucket_arn = getatt('DrFrontendBucket', 'Arn')
    source_arn = sub('arn:${AWS::Partition}:s3:::${SourceBucket}')
    return {'AWSTemplateFormatVersion': '2010-09-09',
        'Description': 'CloudHub disaster recovery in the recovery Region: replicated frontend and catalog snapshot',
        'Rules': {'RecoveryRegion': {'Assertions': [{'Assert': {'Fn::Equals': [ref('AWS::Region'), RECOVERY]},
                                                      'AssertDescription': f'Deploy in {RECOVERY}, away from the primary Region'}]}},
        'Parameters': {
            'SourceBucket': {'Type': 'String', 'Description': 'Private frontend bucket in the primary Region'},
            'DistributionId': {'Type': 'String', 'AllowedPattern': 'E[A-Z0-9]+'},
            'CatalogUrl': {'Type': 'String', 'Default': 'https://api.cloudhub1.me/public/catalog'}},
        'Resources': {
            'DrFrontendBucket': {'Type': 'AWS::S3::Bucket', 'DeletionPolicy': 'Retain', 'UpdateReplacePolicy': 'Retain', 'Properties': {
                'BucketName': sub(BUCKET_NAME),
                'VersioningConfiguration': {'Status': 'Enabled'},
                'BucketEncryption': {'ServerSideEncryptionConfiguration': [{'ServerSideEncryptionByDefault': {'SSEAlgorithm': 'AES256'}}]},
                'PublicAccessBlockConfiguration': {'BlockPublicAcls': True, 'BlockPublicPolicy': True, 'IgnorePublicAcls': True, 'RestrictPublicBuckets': True},
                'OwnershipControls': {'Rules': [{'ObjectOwnership': 'BucketOwnerEnforced'}]},
                'LifecycleConfiguration': {'Rules': [{'Id': 'expire-old-versions', 'Status': 'Enabled',
                    'NoncurrentVersionExpiration': {'NoncurrentDays': 30},
                    'AbortIncompleteMultipartUpload': {'DaysAfterInitiation': 1}}]}}},
            'DrFrontendBucketPolicy': {'Type': 'AWS::S3::BucketPolicy', 'Properties': {'Bucket': ref('DrFrontendBucket'), 'PolicyDocument': {
                'Version': '2012-10-17', 'Statement': [
                    {'Sid': 'CloudFrontOriginAccessControl', 'Effect': 'Allow', 'Principal': {'Service': 'cloudfront.amazonaws.com'},
                     'Action': 's3:GetObject', 'Resource': sub('${DrFrontendBucket.Arn}/*'),
                     'Condition': {'StringEquals': {'AWS:SourceArn': sub('arn:${AWS::Partition}:cloudfront::${AWS::AccountId}:distribution/${DistributionId}')}}},
                    {'Sid': 'TlsOnly', 'Effect': 'Deny', 'Principal': '*', 'Action': 's3:*',
                     'Resource': [bucket_arn, sub('${DrFrontendBucket.Arn}/*')], 'Condition': {'Bool': {'aws:SecureTransport': 'false'}}}]}}},
            'ReplicationRole': {'Type': 'AWS::IAM::Role', 'Properties': {
                'Description': 'S3 Cross-Region Replication of the CloudHub frontend into the recovery Region',
                'AssumeRolePolicyDocument': {'Version': '2012-10-17', 'Statement': [{'Effect': 'Allow',
                    'Principal': {'Service': 's3.amazonaws.com'}, 'Action': 'sts:AssumeRole',
                    'Condition': {'StringEquals': {'aws:SourceAccount': ref('AWS::AccountId')}}}]},
                'Policies': [{'PolicyName': 'replicate-frontend', 'PolicyDocument': {'Version': '2012-10-17', 'Statement': [
                    {'Effect': 'Allow', 'Action': ['s3:GetReplicationConfiguration', 's3:ListBucket'], 'Resource': source_arn},
                    {'Effect': 'Allow', 'Action': ['s3:GetObjectVersionForReplication', 's3:GetObjectVersionAcl', 's3:GetObjectVersionTagging'],
                     'Resource': sub('arn:${AWS::Partition}:s3:::${SourceBucket}/*')},
                    {'Effect': 'Allow', 'Action': ['s3:ReplicateObject', 's3:ReplicateDelete', 's3:ReplicateTags'],
                     'Resource': sub('${DrFrontendBucket.Arn}/*')}]}}]}},
            'SnapshotRole': {'Type': 'AWS::IAM::Role', 'Properties': {
                'AssumeRolePolicyDocument': {'Version': '2012-10-17', 'Statement': [{'Effect': 'Allow',
                    'Principal': {'Service': 'lambda.amazonaws.com'}, 'Action': 'sts:AssumeRole'}]},
                'Policies': [{'PolicyName': 'write-snapshot', 'PolicyDocument': {'Version': '2012-10-17', 'Statement': [
                    {'Effect': 'Allow', 'Action': 's3:PutObject', 'Resource': sub('${DrFrontendBucket.Arn}/' + SNAPSHOT_KEY)},
                    {'Effect': 'Allow', 'Action': ['logs:CreateLogStream', 'logs:PutLogEvents'], 'Resource': getatt('SnapshotLogs', 'Arn')}]}}]}},
            'SnapshotLogs': {'Type': 'AWS::Logs::LogGroup', 'Properties': {
                'LogGroupName': sub('/aws/lambda/${AWS::StackName}-catalog-snapshot'), 'RetentionInDays': 30}},
            'SnapshotFunction': {'Type': 'AWS::Lambda::Function', 'DependsOn': 'SnapshotLogs', 'Properties': {
                'FunctionName': sub('${AWS::StackName}-catalog-snapshot'),
                'Description': 'Stores the public catalog in the recovery Region for CloudFront failover',
                'Runtime': 'python3.13', 'Handler': 'index.handler', 'MemorySize': 256, 'Timeout': 30,
                'Architectures': ['arm64'], 'Role': getatt('SnapshotRole', 'Arn'),
                'Environment': {'Variables': {'BUCKET': ref('DrFrontendBucket'), 'KEY': SNAPSHOT_KEY, 'CATALOG_URL': ref('CatalogUrl')}},
                'Code': {'ZipFile': SNAPSHOT_CODE}}},
            'SchedulerRole': {'Type': 'AWS::IAM::Role', 'Properties': {
                'AssumeRolePolicyDocument': {'Version': '2012-10-17', 'Statement': [{'Effect': 'Allow',
                    'Principal': {'Service': 'scheduler.amazonaws.com'}, 'Action': 'sts:AssumeRole',
                    'Condition': {'StringEquals': {'aws:SourceAccount': ref('AWS::AccountId')}}}]},
                'Policies': [{'PolicyName': 'invoke-snapshot', 'PolicyDocument': {'Version': '2012-10-17', 'Statement': [
                    {'Effect': 'Allow', 'Action': 'lambda:InvokeFunction', 'Resource': getatt('SnapshotFunction', 'Arn')}]}}]}},
            'SnapshotSchedule': {'Type': 'AWS::Scheduler::Schedule', 'Properties': {
                'Description': 'Refresh the recovery copy of the public catalog',
                'ScheduleExpression': SNAPSHOT_RATE, 'FlexibleTimeWindow': {'Mode': 'OFF'},
                'Target': {'Arn': getatt('SnapshotFunction', 'Arn'), 'RoleArn': getatt('SchedulerRole', 'Arn'),
                           'RetryPolicy': {'MaximumRetryAttempts': 2, 'MaximumEventAgeInSeconds': 600}}}}},
        'Outputs': {
            'BucketName': {'Value': ref('DrFrontendBucket')},
            'BucketArn': {'Value': bucket_arn},
            'BucketRegionalDomain': {'Value': getatt('DrFrontendBucket', 'RegionalDomainName')},
            'ReplicationRoleArn': {'Value': getatt('ReplicationRole', 'Arn')},
            'SnapshotFunctionName': {'Value': ref('SnapshotFunction')}}}


def _bodies(items):
    return [i['Fn::If'][1] if 'Fn::If' in i else i for i in items]


def attach_failover(template, primary_origin='private-s3', api_origin='ui-context-api'):
    """Add the recovery bucket as a second origin and route static files and the
    public catalog through origin groups. Origin groups only serve GET/HEAD/OPTIONS,
    so only read-only behaviors are moved; /ui-context stays on the API alone."""
    resources = template['Resources']
    config = resources['FrontendDistribution']['Properties']['DistributionConfig']
    origins = _bodies(config['Origins'])
    by_id = {o['Id']: o for o in origins}
    if primary_origin not in by_id:
        raise ValueError(f'Distribution has no {primary_origin} origin')
    primary = by_id[primary_origin]
    template['Parameters']['DrBucketDomain'] = {'Type': 'String', 'AllowedPattern': r'[a-z0-9.-]+\.s3\.' + RECOVERY + r'\.amazonaws\.com',
        'Description': 'Regional domain of the recovery bucket (stack cloudhub-dr-tokyo, output BucketRegionalDomain)'}
    dr = {'Id': DR_ORIGIN, 'DomainName': ref('DrBucketDomain'), 'S3OriginConfig': {'OriginAccessIdentity': ''},
          'OriginAccessControlId': primary['OriginAccessControlId'],
          'ConnectionAttempts': 3, 'ConnectionTimeout': 10}
    config['Origins'] = [o for o in config['Origins'] if (o['Fn::If'][1] if 'Fn::If' in o else o)['Id'] != DR_ORIGIN] + [dr]

    def group(gid, members, codes):
        return {'Id': gid, 'FailoverCriteria': {'StatusCodes': {'Quantity': len(codes), 'Items': codes}},
                'Members': {'Quantity': len(members), 'Items': [{'OriginId': m} for m in members]}}
    groups = [group(FRONTEND_GROUP, [primary_origin, DR_ORIGIN], FRONTEND_FAILOVER_CODES)]
    behaviors = [config['DefaultCacheBehavior']] + _bodies(config.get('CacheBehaviors', []))
    catalog = [b for b in behaviors if b.get('PathPattern') == '/public/catalog']
    if catalog and api_origin in by_id:
        groups.append(group(CATALOG_GROUP, [api_origin, DR_ORIGIN], API_FAILOVER_CODES))
    config['OriginGroups'] = {'Quantity': len(groups), 'Items': groups}
    for b in behaviors:
        if b.get('TargetOriginId') == primary_origin:
            b['TargetOriginId'] = FRONTEND_GROUP
        elif b.get('PathPattern') == '/public/catalog' and len(groups) == 2:
            b['TargetOriginId'] = CATALOG_GROUP
        if b['TargetOriginId'] in (FRONTEND_GROUP, CATALOG_GROUP):
            methods = set(b.get('AllowedMethods', ['GET', 'HEAD']))
            if not methods <= {'GET', 'HEAD', 'OPTIONS'}:
                raise ValueError(f"Origin groups are read-only; behavior {b.get('PathPattern', 'default')} allows {sorted(methods)}")
    return template


def replica_commands(table, source_bucket, dr_bucket_arn, role_arn):
    """Changes outside CloudFormation, reviewed and run once (see docs/multi-region-dr.md).
    The metadata table and the frontend bucket are not managed by any stack template
    that sets these properties, so no stack drifts."""
    rule = {'Role': role_arn, 'Rules': [{'ID': 'frontend-to-recovery', 'Priority': 1, 'Status': 'Enabled',
            'Filter': {}, 'DeleteMarkerReplication': {'Status': 'Enabled'},
            'Destination': {'Bucket': dr_bucket_arn}}]}
    return [
        f'aws dynamodb update-table --region {PRIMARY} --table-name {table} --stream-specification StreamEnabled=true,StreamViewType=NEW_AND_OLD_IMAGES',
        f'aws dynamodb update-table --region {PRIMARY} --table-name {table} --replica-updates \'[{{"Create":{{"RegionName":"{RECOVERY}"}}}}]\'',
        f'aws dynamodb update-continuous-backups --region {RECOVERY} --table-name {table} --point-in-time-recovery-specification PointInTimeRecoveryEnabled=true',
        f'aws s3api put-bucket-versioning --bucket {source_bucket} --versioning-configuration Status=Enabled',
        f"aws s3api put-bucket-replication --bucket {source_bucket} --replication-configuration '{json.dumps(rule)}'",
        f'aws s3 sync s3://{source_bucket} s3://{dr_bucket_arn.split(":::")[1]} --exclude "{SNAPSHOT_KEY}"']


if __name__ == '__main__':
    out = Path(__file__).resolve().parents[1] / 'infra/dr'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'tokyo.json').write_text(json.dumps(tokyo(), indent=2) + '\n', encoding='utf-8')
    print('Generated', out)
