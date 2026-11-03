"""F03 routes on the existing API; reuse a private evidence bucket."""
import json
from copy import deepcopy
def extend(template):
    resources=template['Resources'];params=template['Parameters']
    params['ApplicationBootstrapPermissionsEnabled']={'Type':'String','Default':'false','AllowedValues':['false','true'],'Description':'Explicit operator approval only: tagged reviewed-app EC2 bootstrap updates in Singapore. Does not enable an application or another Region.'}
    template.setdefault('Conditions',{})['EnableApplicationBootstrapPermissions']={'Fn::Equals':[{'Ref':'ApplicationBootstrapPermissionsEnabled'},'true']}
    owned={'StringEquals':{'aws:RequestedRegion':'ap-southeast-1','aws:ResourceTag/cloudhub:managed':'true'},'StringLike':{'aws:ResourceTag/cloudhub:environment':'env-*'},'Null':{'aws:ResourceTag/cloudhub:owner':'false'}}
    instance={'Fn::Sub':'arn:${AWS::Partition}:ec2:ap-southeast-1:${AWS::AccountId}:instance/*'}
    # CFN sends the named UserData AttributeValue member rather than Attribute.
    # Require that member; EC2 accepts one modified attribute per request.
    userdata=deepcopy(owned);userdata['Null']['ec2:Attribute/UserData']='false'
    resources['ReviewedApplicationBootstrapAccess']={'Type':'AWS::IAM::ManagedPolicy','Condition':'EnableApplicationBootstrapPermissions','Properties':{
        'Description':'Reviewed application bootstrap only: tagged CloudHub EC2/launch templates in Singapore','Roles':[{'Ref':'EnvironmentCfRole'}],
        'PolicyDocument':{'Version':'2012-10-17','Statement':[
            {'Sid':'OwnedApplicationRestart','Effect':'Allow','Action':['ec2:StopInstances','ec2:StartInstances'],'Resource':instance,'Condition':deepcopy(owned)},
            {'Sid':'OwnedApplicationUserDataOnly','Effect':'Allow','Action':'ec2:ModifyInstanceAttribute','Resource':deepcopy(instance),'Condition':userdata},
            {'Sid':'OwnedApplicationLaunchVersion','Effect':'Allow','Action':'ec2:CreateLaunchTemplateVersion','Resource':{'Fn::Sub':'arn:${AWS::Partition}:ec2:ap-southeast-1:${AWS::AccountId}:launch-template/*'},'Condition':deepcopy(owned)}]}}}
    params['RecommendationsEnabled']={'Type':'String','Default':'false','AllowedValues':['true','false'],'Description':'Enable only after workers/ledger understand planning_workload. Does not publish performance evidence.'}
    params['BenchmarksBucket']={'Type':'String','Default':'','AllowedPattern':'^$|[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]',
        'Description':'Existing private operator artifact bucket. No bucket is created; API access must already be scoped to benchmarks/v1/*.'}
    params['RecommendationPolicyJson']={'Type':'String','Default':json.dumps({'schema':1,'resource_headroom_percent':0,'max_benchmark_age_days':30,'observed_quotas':{}},separators=(',',':')),
        'Description':'Operator planning policy, not performance evidence or a quota change. Snapshot observed quotas with date/source.'}
    api=resources['ApiFunction']['Properties'];api['Environment']['Variables'].update(RECOMMENDATIONS_ENABLED={'Ref':'RecommendationsEnabled'},BENCHMARK_BUCKET={'Ref':'BenchmarksBucket'},RECOMMENDATION_POLICY_JSON={'Ref':'RecommendationPolicyJson'})
    params['CloudFrontViewerPricesJson']={'Type':'String','Default':'{"approved":false}','Description':'Reviewed global CloudFront PriceClass_100 envelope with source/version/date; not a replacement for regional origin prices.'}
    resources['CloudFrontViewerPrices']={'Type':'AWS::SSM::Parameter','DeletionPolicy':'Retain','UpdateReplacePolicy':'Retain','Properties':{
        'Name':{'Fn::Sub':'/cloudhub/${AWS::StackName}/regions/cloudfront-viewers'},'Type':'String','Tier':'Standard','Value':{'Ref':'CloudFrontViewerPricesJson'},
        'Description':'CloudHub reviewed edge-price metadata. No account data or secrets.'}}
    for name in ['ApiFunction','WorkerFunction','SweepFunction','ExpiryFunction']:
        if name in resources:resources[name]['Properties']['Environment']['Variables']['CLOUDFRONT_VIEWER_PRICES_PARAMETER']={'Ref':'CloudFrontViewerPrices'}
    for i,(method,path,rate,burst) in enumerate([
        ('GET','/recommendations/schema',5,10),('POST','/recommendations',2,4),
        ('GET','/admin/benchmarks',2,4),('POST','/admin/benchmarks',1,2),('POST','/admin/benchmarks/{benchmark_id}/{control}',1,2),
        ('POST','/environments/{environment_id}/application',1,2)]):
        api['Events']['RecommendationRoute'+str(i)]={'Type':'HttpApi','Properties':{'ApiId':{'Ref':'HttpApi'},'Method':method,'Path':path,
            'RouteSettings':{'ThrottlingRateLimit':rate,'ThrottlingBurstLimit':burst}}}
    # No broad bucket policy or new S3 grant. The current deployment artifact
    # bucket matches the already reviewed CloudHub account/Region object scope.
    # A different retained bucket needs an explicit scoped IAM review first.
