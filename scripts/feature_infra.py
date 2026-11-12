"""IAM and routes for browser terminal, EC2 resize and the cost series.

Least privilege:
- API: ssm:StartSession only on instances tagged cloudhub:managed=true with the
  default Session Manager shell document; TerminateSession only on sessions
  started by this API function.
- Worker: read the original environment template before an InstanceType update.
- CloudFormation execution role: stop/start/modify only managed instances.
"""


def sub(text): return {'Fn::Sub': text}


def statement(actions, resource='*', condition=None):
    body = {'Effect': 'Allow', 'Action': actions, 'Resource': resource}
    if condition:
        body['Condition'] = condition
    return body


MANAGED = {'StringEquals': {'ssm:resourceTag/cloudhub:managed': 'true'}}
EC2_MANAGED = {'StringEquals': {'ec2:ResourceTag/cloudhub:managed': 'true'}}

ROUTES = [('GET', '/environments/{environment_id}/{feature}'),
          ('POST', '/environments/{environment_id}/terminal/{session_id}')]


def api_statements():
    return [
        statement('ssm:StartSession', sub('arn:${AWS::Partition}:ec2:*:${AWS::AccountId}:instance/*'), MANAGED),
        statement('ssm:StartSession', sub('arn:${AWS::Partition}:ssm:*:${AWS::AccountId}:document/SSM-SessionManagerRunShell'),
                  {'BoolIfExists': {'ssm:SessionDocumentAccessCheck': 'true'}}),
        statement('ssm:TerminateSession', sub('arn:${AWS::Partition}:ssm:*:${AWS::AccountId}:session/${AWS::StackName}-api-*')),
    ]


def extend(template):
    resources = template['Resources']
    api = resources['ApiFunction']['Properties']
    api['Policies'].append({'Version': '2012-10-17', 'Statement': api_statements()})
    for index, (method, path) in enumerate(ROUTES):
        api['Events']['FeatureRoute' + str(index)] = {'Type': 'HttpApi', 'Properties': {
            'ApiId': {'Ref': 'HttpApi'}, 'Method': method, 'Path': path}}
    resources['WorkerFunction']['Properties']['Policies'].append({'Version': '2012-10-17', 'Statement': [
        statement('cloudformation:GetTemplate', sub('arn:${AWS::Partition}:cloudformation:${AWS::Region}:${AWS::AccountId}:stack/cloudhub-env-*/*'))]})
    # The execution role carries chunked managed policies (infra_extensions); add one more.
    resources['EnvironmentResizePolicy'] = {'Type': 'AWS::IAM::ManagedPolicy', 'Properties': {
        'Description': 'InstanceType change of CloudHub-managed EC2 through the environment stack',
        'Roles': [{'Ref': 'EnvironmentCfRole'}], 'PolicyDocument': {'Version': '2012-10-17', 'Statement': [
            statement(['ec2:ModifyInstanceAttribute', 'ec2:StopInstances', 'ec2:StartInstances'], '*',
                      {'StringEquals': {**EC2_MANAGED['StringEquals'], 'aws:RequestedRegion': {'Ref': 'AWS::Region'}}})]}}}
    return template
