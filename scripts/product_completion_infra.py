"""Pure IaC extension. Feature gates default closed; no AWS mutations."""
def extend(template):
    r=template['Resources'];params=template['Parameters']
    for name in ['ContinuousEnabled','DirectUploadEnabled']:
        params[name]={'Type':'String','Default':'false','AllowedValues':['true','false']}
    for name in ['ApiFunction','WorkerFunction','SweepFunction','ExpiryFunction']:
        r[name]['Properties']['Environment']['Variables'].update({
            'CONTINUOUS_ENABLED':{'Ref':'ContinuousEnabled'},'DIRECT_UPLOAD_ENABLED':{'Ref':'DirectUploadEnabled'}})
    r['ApiFunction']['Properties']['Environment']['Variables']['ASYNC_DISPATCH_FUNCTION']={'Fn::GetAtt':['ExpiryFunction','Arn']}
    r['ApiFunction']['Properties']['Policies'][0]['Statement'].append({'Effect':'Allow','Action':'lambda:InvokeFunction','Resource':{'Fn::GetAtt':['ExpiryFunction','Arn']}})
    bucket=r['S3BackupBucket']['Properties']
    origin=template['Resources']['HttpApi']['Properties']['CorsConfiguration']['AllowOrigins'][0]
    bucket['CorsConfiguration']={'CorsRules':[{'AllowedOrigins':[origin],'AllowedMethods':['POST'],
        'AllowedHeaders':['*'],'ExposedHeaders':['ETag','x-amz-version-id'],'MaxAge':120}]}
    bucket['VersioningConfiguration']={'Status':'Enabled'}
    bucket.setdefault('LifecycleConfiguration',{'Rules':[]})['Rules'].append({
        'Id':'ExpireIsolatedUploads','Status':'Enabled','Prefix':'uploads/',
        'ExpirationInDays':1,'NoncurrentVersionExpiration':{'NoncurrentDays':1},
        'AbortIncompleteMultipartUpload':{'DaysAfterInitiation':1}})
    upload=[{'Fn::Sub':'${S3BackupBucket.Arn}/uploads/env-*/upload-*'},*({'Fn::Sub':'arn:${AWS::Partition}:s3:::cloudhub-${AWS::AccountId}-'+region+'-backup/uploads/env-*/upload-*'} for region in ['ap-northeast-1','us-east-1'])]
    for name in ['ApiFunction','WorkerFunction','SweepFunction']:
        statements=r[name]['Properties']['Policies'][0]['Statement']
        statements.append({'Effect':'Allow','Action':['s3:GetObject','s3:GetObjectVersion','s3:PutObject'],
                           'Resource':upload})
    for name in ['WorkerFunction','SweepFunction']:
        r[name]['Properties']['Policies'][0]['Statement'].append({'Effect':'Allow',
            'Action':['cloudfront:GetDistributionConfig'],
            'Resource':{'Fn::Sub':'arn:${AWS::Partition}:cloudfront::${AWS::AccountId}:distribution/*'},
            'Condition':{'StringEquals':{'aws:ResourceTag/cloudhub:managed':'true'}}})
    function_scope={'Fn::Sub':'arn:${AWS::Partition}:cloudfront::${AWS::AccountId}:function/cloudhub-env-*-content'}
    r['ProductContentPolicy']={'Type':'AWS::IAM::ManagedPolicy','Properties':{'Roles':[{'Ref':'EnvironmentCfRole'}],'PolicyDocument':{'Version':'2012-10-17','Statement':[{
        'Effect':'Allow','Action':['cloudfront:DescribeFunction','cloudfront:PublishFunction','cloudfront:UpdateFunction','cloudfront:DeleteFunction','cloudfront:GetFunction','cloudfront:TagResource','cloudfront:UntagResource','cloudfront:ListTagsForResource'],
        'Resource':function_scope},{'Effect':'Allow','Action':'cloudfront:CreateFunction','Resource':'*','Condition':{'StringEquals':{'aws:RequestTag/cloudhub:managed':'true'}}}]}}}
    for name in ['WorkerFunction','SweepFunction']:
        r[name]['Properties']['Policies'][0]['Statement'].append({'Effect':'Allow','Action':['cloudfront:DescribeFunction','cloudfront:GetFunction','cloudfront:UpdateFunction','cloudfront:PublishFunction'],'Resource':function_scope})
    r['Table']['Properties'].setdefault('TimeToLiveSpecification',{'AttributeName':'ttl','Enabled':True})
    # Advisory log delivery uses the existing CloudWatch -> operator SNS path.
    # No worker SNS permissions, new recipient, or destructive budget action.
    r['ContinuousWarningMetric']={'Type':'AWS::Logs::MetricFilter','Properties':{
        'LogGroupName':{'Ref':'SweepFunctionLog'},'FilterPattern':'{ $.event = "CloudHubContinuousWarning" }',
        'MetricTransformations':[{'MetricNamespace':'CloudHub','MetricName':'ContinuousWarning','MetricValue':'1'}]}}
    r['ContinuousWarningAlarm']={'Type':'AWS::CloudWatch::Alarm','Properties':{
        'AlarmDescription':'CloudHub continuous forecast warning. Source preserved; charges may continue. See owned in-app notification for details.',
        'Namespace':'CloudHub','MetricName':'ContinuousWarning','Statistic':'Sum','Period':60,'EvaluationPeriods':1,
        'Threshold':1,'ComparisonOperator':'GreaterThanOrEqualToThreshold','TreatMissingData':'notBreaching',
        'AlarmActions':[{'Ref':'AlertTopic'}]}}
    return template
