"""Change the EC2 instance type of a running T01/T05 environment.

The target must be another published profile with the same root and data
disks, so storage and data are untouched. The change goes through the
environment's own CloudFormation stack: the current template is read back and
only Instance.InstanceType is replaced. EC2 performs a stop/start (instance ID,
EBS volumes and data are kept; the public IPv4 can change). A failed update
rolls back to the previous type.

Consent is a two-step exchange: ``preview`` returns the cost difference for the
rest of the current period; ``begin`` must echo that exact amount.
"""
import json
from decimal import Decimal

from .errors import HubError

RESIZABLE = {'T01', 'T05'}
DISKS = ('root_gib', 'data_gib')


def _profiles(tid):
    from .catalog import configuration_profiles
    return configuration_profiles(tid)


def _remaining_hours(service, env):
    deadline = env.get('deadline')
    if not deadline:
        return Decimal(1)
    seconds = max(0, int(deadline) - int(service.clock()))
    return max(Decimal(1) / 12, Decimal(seconds) / 3600)


def _delta(service, env, target):
    from .catalog import environment_configuration
    estimator = service.estimator_for(env)
    hours = _remaining_hours(service, env)
    old = estimator.estimate(env['template_id'], hours, renewal=True, backup=False, configuration=environment_configuration(env))
    new = estimator.estimate(env['template_id'], hours, renewal=True, backup=False, configuration=target)
    if not old['approved'] or not new['approved']:
        return None, hours
    return new['total_milliusd'] - old['total_milliusd'], hours


def targets(service, owner, eid):
    """Resize options for an owned environment, with verification and cost difference."""
    from .catalog import environment_configuration
    env = service.owned('E', eid, owner)
    if env['template_id'] not in RESIZABLE:
        return {'environment_id': eid, 'supported': False, 'targets': []}
    current = environment_configuration(env)
    region = service.region_for(env)
    rows = []
    for profile in _profiles(env['template_id']):
        cfg = profile['configuration']
        if any(cfg[k] != current[k] for k in DISKS) or cfg['instance_type'] == current['instance_type']:
            continue
        delta, hours = _delta(service, env, cfg)
        rows.append({'configuration_id': profile['id'], 'instance_type': cfg['instance_type'], 'label': profile['label'],
                     'verified': service.configuration_is_verified(env['template_id'], cfg, region),
                     'delta_milliusd': delta, 'remaining_hours': str(hours), 'prices_available': delta is not None})
    return {'environment_id': eid, 'supported': True, 'current_instance_type': current['instance_type'],
            'interruption': 'EC2 stop/start; instance ID, disks and data are kept; public IPv4 may change.',
            'targets': rows}


def begin(service, owner, eid, key, body, is_admin=False):
    from .service import retry
    from .catalog import environment_configuration
    if not isinstance(body, dict) or set(body) != {'configuration_id', 'expected_revision', 'expected_delta_milliusd', 'confirmed'} or body['confirmed'] is not True:
        raise HubError('RESIZE_CONSENT_REQUIRED', 'Xem trước chi phí rồi xác nhận đổi cấu hình, gồm khoảng gián đoạn khi máy khởi động lại.')

    def transaction():
        env = service.owned('E', eid, owner)
        _, _, old = service.idempotency(owner, key, eid + '/resize', body)
        if old:
            return service.owned('O', old['operation_id'], owner)
        if env['template_id'] not in RESIZABLE:
            raise HubError('RESIZE_UNSUPPORTED', 'Chỉ máy Linux (T01) và website trên máy chủ (T05) đổi được loại máy.', 409)
        service._assert_mutable(env, body)
        current = environment_configuration(env)
        target = next((p['configuration'] for p in _profiles(env['template_id']) if p['id'] == body['configuration_id']), None)
        if target is None or any(target[k] != current[k] for k in DISKS) or target['instance_type'] == current['instance_type']:
            raise HubError('RESIZE_INVALID', 'Chọn một loại máy khác có cùng dung lượng ổ đĩa.', 409)
        validation = is_admin and env.get('validation_run') is True and env['template_id'] in service.validation
        if not service.configuration_is_verified(env['template_id'], target, service.region_for(env)) and not validation:
            raise HubError('CONFIGURATION_UNVERIFIED', 'Loại máy này chưa được kiểm chứng trên AWS tại Region của môi trường.', 409)
        delta, _ = _delta(service, env, target)
        if delta is None:
            raise HubError('PRICES_UNAPPROVED', 'Chưa có đơn giá được duyệt cho loại máy này.', 409)
        if delta != body['expected_delta_milliusd']:
            raise HubError('QUOTE_CHANGED', 'Chi phí chênh lệch đã thay đổi; xem trước lại.', 409, {'delta_milliusd': delta})
        rows = []
        if delta > 0:
            from .spend_guard import assert_open
            assert_open(service)
            rows = list(service.quota(owner, delta, 0))
            env['estimated_committed_milliusd'] = service._committed(env) + delta
            env['estimate']['total_milliusd'] = env['estimated_committed_milliusd']
        env['status'] = 'RESIZING'
        return service._management(env, key, 'resize', body, 'RESIZE', extra_rows=rows, fields={
            'resize_from': current, 'resize_target': target, 'resize_step': 'UPDATE_STACK', 'delta_milliusd': delta,
            'cost_scope': 'Difference for the rest of the current period; later periods use the new instance price.'})
    return retry(transaction)


def _instance_resource(template):
    found = [(name, r) for name, r in template.get('Resources', {}).items() if r.get('Type') == 'AWS::EC2::Instance']
    if len(found) != 1:
        raise HubError('RESIZE_RECONCILE_REQUIRED', 'Expected exactly one EC2 instance in the environment stack.', 409)
    return found[0]


def step(driver, env, op, before_mutation=lambda: None):
    """One bounded step. Returns True when the instance runs the new type and passed readiness."""
    stage = op['resize_step']
    stack = driver.assert_stack(env)
    if not stack:
        raise HubError('RESIZE_FAILED', 'Owned stack missing; environment metadata is preserved.', 409)
    target = op['resize_target']['instance_type']
    if stage == 'UPDATE_STACK':
        if stack['StackStatus'].endswith('_IN_PROGRESS'):
            return False
        body = driver.cloudformation.get_template(StackName=driver.stack_name(env), TemplateStage='Original')['TemplateBody']
        template = json.loads(body) if isinstance(body, str) else body
        _, instance = _instance_resource(template)
        op['resize_step'] = 'WAIT_STACK'
        if instance['Properties'].get('InstanceType') == target:
            return False  # an earlier attempt already submitted this exact change
        instance['Properties']['InstanceType'] = target
        before_mutation()
        driver.cloudformation.update_stack(StackName=driver.stack_name(env), TemplateBody=json.dumps(template),
            Capabilities=['CAPABILITY_NAMED_IAM'], RoleARN=driver.settings['cf_role_arn'],
            ClientRequestToken=op['operation_id'] + '-resize-g' + str(op.get('generation', 0)),
            Parameters=[{'ParameterKey': p['ParameterKey'], 'UsePreviousValue': True} for p in stack.get('Parameters', [])])
        return False
    if stage == 'WAIT_STACK':
        status = stack['StackStatus']
        if status.endswith('_IN_PROGRESS'):
            return False
        if status == 'UPDATE_ROLLBACK_COMPLETE':
            raise HubError('RESIZE_ROLLED_BACK', 'AWS rejected the new instance type; CloudFormation restored the previous one.', 409)
        if status != 'UPDATE_COMPLETE':
            raise HubError('RESIZE_FAILED', 'CloudFormation did not apply the new instance type (' + status + '); previous type kept.', 409)
        instance = driver.ec2.describe_instances(InstanceIds=[env['instance_id']])['Reservations'][0]['Instances'][0]
        if instance.get('InstanceType') != target:
            raise HubError('RESIZE_RECONCILE_REQUIRED', 'Stack updated but the instance reports a different type.', 409)
        op['resize_step'] = 'READINESS'
        return False
    if stage == 'READINESS':
        return bool(driver.ready(env, op, None))
    raise HubError('RESIZE_RECONCILE_REQUIRED', 'Unknown resize step.', 409)
