"""Controlled chaos experiment: a full API outage, with guard rails and automatic rollback.

AWS Fault Injection Service is not yet available on this account (it returns
SubscriptionRequiredException until AWS finishes verifying the account), so the
experiment is orchestrated with Step Functions SDK integrations, following the
same model as an FIS experiment template:

* Fault: reserved concurrency 0 on the API Lambda, so every API request fails
  (HTTP API answers 503). Nothing is deleted and no code changes.
* Preconditions: the function has no reserved concurrency of its own (the
  rollback must restore exactly the previous state) and no guard alarm is firing.
* Stop condition: checked every 15 s. If a guard alarm fires (by default:
  a lifecycle workflow of a real user failed) the fault is removed at once.
* Duration: 30-600 s, then rollback (DeleteFunctionConcurrency, retried) and a
  verification that the reserved concurrency is gone.
* Safety net: if the execution is aborted by hand or times out before the
  rollback state runs, EventBridge starts a separate restore workflow.

Hypothesis tested (docs/multi-region-dr.md): guests still load the site and the
catalog (edge cache, then Tokyo snapshot through the origin group), health
checks, Lambda-throttle and SLO burn-rate alarms fire, and the API is healthy
again within a minute of the rollback.
"""
import json
from pathlib import Path

HOLD_SECONDS = 15
MAX_DURATION = 600


def ref(name): return {'Ref': name}
def sub(text): return {'Fn::Sub': text}
def getatt(name, attr): return {'Fn::GetAtt': [name, attr]}


def sdk(service, action):
    return f'arn:aws:states:::aws-sdk:{service}:{action}'


RESTORE_RETRY = [{'ErrorEquals': ['States.ALL'], 'IntervalSeconds': 2, 'BackoffRate': 2, 'MaxAttempts': 6}]


def experiment_definition():
    catch = [{'ErrorEquals': ['States.ALL'], 'ResultPath': '$.error', 'Next': 'RemoveFault'}]
    guard = {'Type': 'Task', 'Resource': sdk('cloudwatch', 'describeAlarms'),
             'Parameters': {'AlarmNames.$': '$.guard_alarms', 'StateValue': 'ALARM'},
             'ResultSelector': {'firing.$': 'States.ArrayLength($.MetricAlarms)'}, 'ResultPath': '$.guard'}
    return {
        'Comment': 'CloudHub chaos experiment: API outage with stop condition and rollback',
        'TimeoutSeconds': MAX_DURATION + 300,
        'StartAt': 'ValidateInput',
        'States': {
            'ValidateInput': {'Type': 'Choice', 'Choices': [{'And': [
                {'Variable': '$.duration_seconds', 'IsNumeric': True},
                {'Variable': '$.duration_seconds', 'NumericGreaterThanEquals': 30},
                {'Variable': '$.duration_seconds', 'NumericLessThanEquals': MAX_DURATION}], 'Next': 'AddGuards'}],
                'Default': 'InvalidInput'},
            'InvalidInput': {'Type': 'Fail', 'Error': 'InvalidInput', 'Cause': f'duration_seconds must be 30-{MAX_DURATION}'},
            'AddGuards': {'Type': 'Pass', 'Parameters': {'duration_seconds.$': '$.duration_seconds',
                'guard_alarms.$': '$$.Execution.Input.guard_alarms', 'elapsed': 0}, 'ResultPath': '$', 'Next': 'ReadBaseline'},
            'ReadBaseline': {'Type': 'Task', 'Resource': sdk('lambda', 'getFunctionConcurrency'),
                'Parameters': {'FunctionName': '${TargetFunction}'}, 'ResultPath': '$.baseline', 'Next': 'BaselineFree'},
            'BaselineFree': {'Type': 'Choice', 'Choices': [
                {'Variable': '$.baseline.ReservedConcurrentExecutions', 'IsPresent': True, 'Next': 'BaselineHasReserved'}],
                'Default': 'GuardBefore'},
            'BaselineHasReserved': {'Type': 'Fail', 'Error': 'PreconditionFailed',
                'Cause': 'Target already has reserved concurrency; rollback could not restore it exactly'},
            'GuardBefore': {**guard, 'Next': 'GuardsQuiet'},
            'GuardsQuiet': {'Type': 'Choice', 'Choices': [{'Variable': '$.guard.firing', 'NumericGreaterThan': 0, 'Next': 'GuardAlreadyFiring'}],
                'Default': 'InjectFault'},
            'GuardAlreadyFiring': {'Type': 'Fail', 'Error': 'PreconditionFailed', 'Cause': 'A guard alarm is already in ALARM'},
            'InjectFault': {'Type': 'Task', 'Resource': sdk('lambda', 'putFunctionConcurrency'),
                'Parameters': {'FunctionName': '${TargetFunction}', 'ReservedConcurrentExecutions': 0},
                'ResultPath': '$.injected', 'Catch': catch, 'Next': 'Hold'},
            'Hold': {'Type': 'Wait', 'Seconds': HOLD_SECONDS, 'Next': 'CheckGuards'},
            'CheckGuards': {**guard, 'Catch': catch, 'Next': 'StopOrContinue'},
            'StopOrContinue': {'Type': 'Choice', 'Choices': [
                {'Variable': '$.guard.firing', 'NumericGreaterThan': 0, 'Next': 'StopConditionMet'}],
                'Default': 'Tick'},
            'StopConditionMet': {'Type': 'Pass', 'Result': 'stop condition: guard alarm fired', 'ResultPath': '$.stopped', 'Next': 'RemoveFault'},
            'Tick': {'Type': 'Pass', 'Parameters': {'duration_seconds.$': '$.duration_seconds', 'guard_alarms.$': '$.guard_alarms',
                'baseline.$': '$.baseline', 'elapsed.$': f'States.MathAdd($.elapsed, {HOLD_SECONDS})'}, 'Next': 'DurationReached'},
            'DurationReached': {'Type': 'Choice', 'Choices': [
                {'Variable': '$.elapsed', 'NumericGreaterThanEqualsPath': '$.duration_seconds', 'Next': 'RemoveFault'}],
                'Default': 'Hold'},
            'RemoveFault': {'Type': 'Task', 'Resource': sdk('lambda', 'deleteFunctionConcurrency'),
                'Parameters': {'FunctionName': '${TargetFunction}'}, 'Retry': RESTORE_RETRY, 'ResultPath': None, 'Next': 'VerifyRestored'},
            'VerifyRestored': {'Type': 'Task', 'Resource': sdk('lambda', 'getFunctionConcurrency'),
                'Parameters': {'FunctionName': '${TargetFunction}'}, 'ResultPath': '$.after', 'Next': 'Restored'},
            'Restored': {'Type': 'Choice', 'Choices': [
                {'Variable': '$.after.ReservedConcurrentExecutions', 'IsPresent': True, 'Next': 'RestoreFailed'},
                {'Variable': '$.stopped', 'IsPresent': True, 'Next': 'StoppedByGuard'},
                {'Variable': '$.error', 'IsPresent': True, 'Next': 'ErrorRolledBack'}],
                'Default': 'Completed'},
            'RestoreFailed': {'Type': 'Fail', 'Error': 'RestoreFailed', 'Cause': 'Reserved concurrency still set; restore manually'},
            'StoppedByGuard': {'Type': 'Fail', 'Error': 'StopConditionMet', 'Cause': 'Guard alarm fired; fault removed early'},
            'ErrorRolledBack': {'Type': 'Fail', 'Error': 'ExperimentError', 'Cause': 'Fault removed after an error'},
            'Completed': {'Type': 'Succeed'}}}


def restore_definition():
    return {'Comment': 'Safety net: remove the injected fault if the experiment was aborted or timed out',
            'StartAt': 'RemoveFault', 'States': {
                'RemoveFault': {'Type': 'Task', 'Resource': sdk('lambda', 'deleteFunctionConcurrency'),
                    'Parameters': {'FunctionName': '${TargetFunction}'}, 'Retry': RESTORE_RETRY, 'End': True}}}


def regional():
    function_arn = sub('arn:${AWS::Partition}:lambda:${AWS::Region}:${AWS::AccountId}:function:${TargetFunction}')
    states_trust = {'Version': '2012-10-17', 'Statement': [{'Effect': 'Allow', 'Principal': {'Service': 'states.amazonaws.com'},
        'Action': 'sts:AssumeRole', 'Condition': {'StringEquals': {'aws:SourceAccount': ref('AWS::AccountId')}}}]}
    return {'AWSTemplateFormatVersion': '2010-09-09',
        'Description': 'CloudHub chaos experiment (API outage) with stop condition and automatic rollback',
        'Parameters': {
            'TargetFunction': {'Type': 'String', 'Default': 'cloudhub-pages-live-api'},
            'LifecycleStateMachineArn': {'Type': 'String', 'Description': 'Workflow whose failures abort the experiment'}},
        'Resources': {
            'LifecycleFailureGuard': {'Type': 'AWS::CloudWatch::Alarm', 'Properties': {
                'AlarmName': sub('${AWS::StackName}-guard-lifecycle-failed'),
                'AlarmDescription': 'Stop condition: a real environment workflow failed during the experiment',
                'Namespace': 'AWS/States', 'MetricName': 'ExecutionsFailed',
                'Dimensions': [{'Name': 'StateMachineArn', 'Value': ref('LifecycleStateMachineArn')}],
                'Statistic': 'Sum', 'Period': 60, 'EvaluationPeriods': 1, 'Threshold': 0,
                'ComparisonOperator': 'GreaterThanThreshold', 'TreatMissingData': 'notBreaching'}},
            'ExperimentRole': {'Type': 'AWS::IAM::Role', 'Properties': {'AssumeRolePolicyDocument': states_trust,
                'Policies': [{'PolicyName': 'inject-and-rollback', 'PolicyDocument': {'Version': '2012-10-17', 'Statement': [
                    {'Effect': 'Allow', 'Action': ['lambda:GetFunctionConcurrency', 'lambda:PutFunctionConcurrency',
                                                   'lambda:DeleteFunctionConcurrency'], 'Resource': function_arn},
                    {'Effect': 'Allow', 'Action': 'cloudwatch:DescribeAlarms', 'Resource': '*'}]}}]}},
            'Experiment': {'Type': 'AWS::StepFunctions::StateMachine', 'Properties': {
                'StateMachineName': sub('${AWS::StackName}-api-outage'), 'RoleArn': getatt('ExperimentRole', 'Arn'),
                'DefinitionString': json.dumps(experiment_definition()),
                'DefinitionSubstitutions': {'TargetFunction': ref('TargetFunction')}}},
            'RestoreRole': {'Type': 'AWS::IAM::Role', 'Properties': {'AssumeRolePolicyDocument': states_trust,
                'Policies': [{'PolicyName': 'rollback', 'PolicyDocument': {'Version': '2012-10-17', 'Statement': [
                    {'Effect': 'Allow', 'Action': 'lambda:DeleteFunctionConcurrency', 'Resource': function_arn}]}}]}},
            'Restore': {'Type': 'AWS::StepFunctions::StateMachine', 'Properties': {
                'StateMachineName': sub('${AWS::StackName}-restore'), 'RoleArn': getatt('RestoreRole', 'Arn'),
                'DefinitionString': json.dumps(restore_definition()),
                'DefinitionSubstitutions': {'TargetFunction': ref('TargetFunction')}}},
            'SafetyNetRole': {'Type': 'AWS::IAM::Role', 'Properties': {
                'AssumeRolePolicyDocument': {'Version': '2012-10-17', 'Statement': [{'Effect': 'Allow',
                    'Principal': {'Service': 'events.amazonaws.com'}, 'Action': 'sts:AssumeRole'}]},
                'Policies': [{'PolicyName': 'start-restore', 'PolicyDocument': {'Version': '2012-10-17', 'Statement': [
                    {'Effect': 'Allow', 'Action': 'states:StartExecution', 'Resource': ref('Restore')}]}}]}},
            'SafetyNet': {'Type': 'AWS::Events::Rule', 'Properties': {
                'Description': 'Run the restore workflow when the experiment ends without its own rollback',
                'EventPattern': {'source': ['aws.states'], 'detail-type': ['Step Functions Execution Status Change'],
                                 'detail': {'stateMachineArn': [ref('Experiment')], 'status': ['ABORTED', 'TIMED_OUT']}},
                'Targets': [{'Id': 'restore', 'Arn': ref('Restore'), 'RoleArn': getatt('SafetyNetRole', 'Arn')}]}}},
        'Outputs': {
            'ExperimentArn': {'Value': ref('Experiment')},
            'GuardAlarm': {'Value': ref('LifecycleFailureGuard')},
            'StartInput': {'Value': sub(json.dumps({'duration_seconds': 180, 'guard_alarms': ['${LifecycleFailureGuard}']}))}}}


if __name__ == '__main__':
    out = Path(__file__).resolve().parents[1] / 'infra/chaos'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'regional.json').write_text(json.dumps(regional(), indent=2) + '\n', encoding='utf-8')
    print('Generated', out)
