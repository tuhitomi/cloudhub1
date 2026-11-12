"""IAM role that lets GitHub Actions *propose* a control-plane change set via OIDC.

No long-lived AWS keys are stored in GitHub. The role can upload the packaged
artifact and create/describe/delete change sets for one stack. It cannot execute
a change set, so every deployment still needs a person to review and run
`aws cloudformation execute-change-set` (or the console button).
"""
import json
from pathlib import Path

GITHUB_OIDC = 'token.actions.githubusercontent.com'
ENVIRONMENT = 'aws-changeset'


def template():
    sub = lambda text: {'Fn::Sub': text}
    stack_arn = sub('arn:${AWS::Partition}:cloudformation:${AWS::Region}:${AWS::AccountId}:stack/${StackName}/*')
    return {'AWSTemplateFormatVersion': '2010-09-09',
        'Description': 'GitHub Actions OIDC role that can only propose CloudHub change sets',
        'Parameters': {
            'GitHubRepository': {'Type': 'String', 'Default': 'tuhitomi/cloudhub1', 'AllowedPattern': '[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+'},
            'StackName': {'Type': 'String', 'Default': 'cloudhub', 'AllowedPattern': '[A-Za-z][A-Za-z0-9-]{0,127}'},
            'ArtifactBucket': {'Type': 'String', 'AllowedPattern': '[a-z0-9.-]{3,63}'},
            'CreateOidcProvider': {'Type': 'String', 'AllowedValues': ['true', 'false'], 'Default': 'true',
                'Description': 'false when the account already has the GitHub OIDC provider'}},
        'Conditions': {'NewProvider': {'Fn::Equals': [{'Ref': 'CreateOidcProvider'}, 'true']}},
        'Resources': {
            'GitHubOidcProvider': {'Type': 'AWS::IAM::OIDCProvider', 'Condition': 'NewProvider', 'Properties': {
                'Url': 'https://' + GITHUB_OIDC, 'ClientIdList': ['sts.amazonaws.com']}},
            'ChangeSetRole': {'Type': 'AWS::IAM::Role', 'Properties': {
                'Description': 'Propose (never execute) CloudHub change sets from the aws-changeset GitHub environment',
                'MaxSessionDuration': 3600,
                'AssumeRolePolicyDocument': {'Version': '2012-10-17', 'Statement': [{
                    'Effect': 'Allow', 'Action': 'sts:AssumeRoleWithWebIdentity',
                    'Principal': {'Federated': sub('arn:${AWS::Partition}:iam::${AWS::AccountId}:oidc-provider/' + GITHUB_OIDC)},
                    'Condition': {'StringEquals': {GITHUB_OIDC + ':aud': 'sts.amazonaws.com',
                                                   GITHUB_OIDC + ':sub': sub('repo:${GitHubRepository}:environment:' + ENVIRONMENT)}}}]},
                'Policies': [{'PolicyName': 'propose-change-set', 'PolicyDocument': {'Version': '2012-10-17', 'Statement': [
                    {'Sid': 'ChangeSets', 'Effect': 'Allow', 'Resource': stack_arn, 'Action': [
                        'cloudformation:CreateChangeSet', 'cloudformation:DescribeChangeSet', 'cloudformation:DeleteChangeSet',
                        'cloudformation:ListChangeSets', 'cloudformation:DescribeStacks', 'cloudformation:GetTemplateSummary']},
                    {'Sid': 'SamTransform', 'Effect': 'Allow', 'Action': 'cloudformation:CreateChangeSet',
                     'Resource': sub('arn:${AWS::Partition}:cloudformation:${AWS::Region}:aws:transform/Serverless-2016-10-31')},
                    {'Sid': 'Validate', 'Effect': 'Allow', 'Action': ['cloudformation:ValidateTemplate'], 'Resource': '*'},
                    {'Sid': 'Artifacts', 'Effect': 'Allow', 'Action': ['s3:PutObject', 's3:GetObject'],
                     'Resource': sub('arn:${AWS::Partition}:s3:::${ArtifactBucket}/ci/*')},
                    {'Sid': 'NoExecute', 'Effect': 'Deny', 'Resource': '*', 'Action': [
                        'cloudformation:ExecuteChangeSet', 'cloudformation:UpdateStack', 'cloudformation:CreateStack',
                        'cloudformation:DeleteStack', 'iam:PassRole']}]}}]}}},
        'Outputs': {'RoleArn': {'Value': {'Fn::GetAtt': ['ChangeSetRole', 'Arn']}}}}


if __name__ == '__main__':
    out = Path(__file__).resolve().parents[1] / 'infra/ci/github-changeset-role.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(template(), indent=2) + '\n', encoding='utf-8')
    print('Generated ' + str(out))
