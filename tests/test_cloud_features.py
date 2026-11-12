"""LOCAL only: browser terminal, EC2 resize, RDS Multi-AZ profile and daily cost series."""
import json, sys, unittest
from copy import deepcopy
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'scripts'))
from cloudhub import terminal, resize, spend_guard
from cloudhub.catalog import configuration_profiles, configuration_key, resolve_configuration
from cloudhub.cost import Estimator
from cloudhub.cost_series import series
from cloudhub.errors import HubError
from test_domain import RATES
import test_lifecycle

SMALL = next(p for p in configuration_profiles('T05') if p['id'] == 'small')['configuration']


class FakeSsm:
    def __init__(self):
        self.started, self.ended = [], []

    def start_session(self, **kwargs):
        self.started.append(kwargs)
        return {'SessionId': 'cloudhub-api-' + str(len(self.started)), 'TokenValue': 'one-time', 'StreamUrl': 'wss://ssmmessages.ap-southeast-1.amazonaws.com/v1/data-channel/x'}

    def terminate_session(self, SessionId):
        self.ended.append(SessionId)


# Only the tests defined below run from these classes.
def only_own_tests(cls):
    for name in [n for n in dir(test_lifecycle.LifecycleTests) if n.startswith('test_')]:
        if getattr(cls, name) is getattr(test_lifecycle.LifecycleTests, name):
            setattr(cls, name, None)
    return cls


@only_own_tests
class FeatureBase(test_lifecycle.LifecycleTests):
    def setUp(self):
        super().setUp()
        self.rates = deepcopy(RATES)
        self.service.estimator = Estimator(self.rates)


@only_own_tests
class TerminalTests(FeatureBase):
    def test_owner_starts_session_on_own_instance_and_token_is_not_stored(self):
        env = self.ready(); ssm = FakeSsm()
        started = terminal.start(self.service, 'alice', env['environment_id'], {}, {'ssm': ssm})
        self.assertEqual(ssm.started[0]['Target'], env['instance_id'])
        self.assertNotIn('DocumentName', ssm.started[0])
        self.assertEqual(started['token'], 'one-time')
        row = self.store.get('T#' + started['session_id'])
        self.assertEqual((row['owner_id'], row['status']), ('alice', 'ACTIVE'))
        self.assertNotIn('one-time', json.dumps(row))
        ended = terminal.end(self.service, 'alice', env['environment_id'], started['session_id'], {'ssm': ssm})
        self.assertEqual((ended['status'], ssm.ended), ('ENDED', [started['session_id']]))

    def test_other_owner_unready_and_unsupported_are_refused(self):
        env = self.ready(); ssm = FakeSsm()
        with self.assertRaises(HubError):
            terminal.start(self.service, 'mallory', env['environment_id'], {}, {'ssm': ssm})
        env['status'] = 'PAUSED'; self.store.commit([env], {env['pk']: env['version']})
        with self.assertRaises(HubError) as error:
            terminal.start(self.service, 'alice', env['environment_id'], {}, {'ssm': ssm})
        self.assertEqual(error.exception.code, 'TERMINAL_UNAVAILABLE')
        with self.assertRaises(HubError):
            terminal.start(self.service, 'alice', env['environment_id'], {'node': 3, 'extra': 1}, {'ssm': ssm})
        self.assertEqual(ssm.started, [])

    def test_two_active_sessions_per_environment_and_stale_slots_expire(self):
        env = self.ready(); ssm = FakeSsm()
        for _ in range(2):
            terminal.start(self.service, 'alice', env['environment_id'], {}, {'ssm': ssm})
        with self.assertRaises(HubError) as error:
            terminal.start(self.service, 'alice', env['environment_id'], {}, {'ssm': ssm})
        self.assertEqual(error.exception.code, 'TERMINAL_LIMIT')
        self.now += terminal.STALE_SECONDS + 1
        self.assertEqual(len(terminal.active_sessions(self.service, 'alice', env['environment_id'])), 0)


class FakeCloudFormation:
    def __init__(self, template, statuses):
        self.template, self.statuses, self.updates = template, statuses, []

    def get_template(self, **kwargs):
        return {'TemplateBody': json.dumps(self.template)}

    def update_stack(self, **kwargs):
        self.updates.append(kwargs); self.template = json.loads(kwargs['TemplateBody'])


class FakeEc2:
    def __init__(self, cf):
        self.cf = cf

    def describe_instances(self, InstanceIds):
        kind = self.cf.template['Resources']['Instance']['Properties']['InstanceType']
        return {'Reservations': [{'Instances': [{'InstanceId': InstanceIds[0], 'InstanceType': kind}]}]}


class FakeDriver:
    def __init__(self, status='UPDATE_COMPLETE'):
        self.cloudformation = FakeCloudFormation({'Resources': {'Instance': {'Type': 'AWS::EC2::Instance', 'Properties': {'InstanceType': 't3.micro'}},
            'DataVolume': {'Type': 'AWS::EC2::Volume', 'Properties': {'Size': 8, 'SnapshotId': 'snap-keep'}}}}, [])
        self.ec2 = FakeEc2(self.cloudformation); self.settings = {'cf_role_arn': 'arn:role'}; self.final = status; self.ready_calls = 0

    def stack_name(self, env): return 'cloudhub-' + env['environment_id']

    def assert_stack(self, env):
        status = self.final if self.cloudformation.updates else 'CREATE_COMPLETE'
        return {'StackStatus': status, 'Parameters': [{'ParameterKey': 'A'}]}

    def ready(self, env, op, recovery):
        self.ready_calls += 1; return True


@only_own_tests
class ResizeTests(FeatureBase):
    def verify_small(self):
        self.rates['units']['ec2_hour.t3.small'] = '0.0208'
        self.rates.setdefault('configuration_verifications', {})[configuration_key('T05', SMALL)] = {
            'passed': True, 'provisioning_checks': 2, 'backup_restore_verified': True}

    def ready(self, policy=None, preview=8):
        # Eight hours left in the period so the price difference is visible after rounding.
        env = super().ready(policy, preview)
        env['deadline'] = self.now + 8 * 3600
        self.store.commit([env], {env['pk']: env['version']})
        return self.store.get(env['pk'])

    def body(self, env, delta):
        return {'configuration_id': 'small', 'expected_revision': env['lifecycle_revision'], 'expected_delta_milliusd': delta, 'confirmed': True}

    def test_targets_keep_disks_and_report_verification_and_price(self):
        env = self.ready()
        options = resize.targets(self.service, 'alice', env['environment_id'])
        ids = {t['configuration_id'] for t in options['targets']}
        self.assertEqual(ids, {'small'})
        self.assertTrue(all(not t['verified'] and t['delta_milliusd'] is None for t in options['targets']))
        self.verify_small()
        small = next(t for t in resize.targets(self.service, 'alice', env['environment_id'])['targets'] if t['configuration_id'] == 'small')
        self.assertTrue(small['verified']); self.assertGreater(small['delta_milliusd'], 0)

    def test_unverified_price_change_and_wrong_consent_are_refused(self):
        env = self.ready()
        with self.assertRaises(HubError) as error:
            resize.begin(self.service, 'alice', env['environment_id'], 'resize-key-1', self.body(env, 0))
        self.assertEqual(error.exception.code, 'CONFIGURATION_UNVERIFIED')
        self.verify_small()
        with self.assertRaises(HubError) as error:
            resize.begin(self.service, 'alice', env['environment_id'], 'resize-key-2', self.body(env, 1))
        self.assertEqual(error.exception.code, 'QUOTE_CHANGED')
        with self.assertRaises(HubError):
            resize.begin(self.service, 'alice', env['environment_id'], 'resize-key-3', {**self.body(env, 1), 'confirmed': False})

    def test_resize_reserves_difference_updates_only_instance_type_and_keeps_data(self):
        env = self.ready(); self.verify_small()
        delta = resize.targets(self.service, 'alice', env['environment_id'])['targets'][0]['delta_milliusd']
        reserved = self.store.get('Q#GLOBAL')['reserved_milliusd']
        op = resize.begin(self.service, 'alice', env['environment_id'], 'resize-key-ok', self.body(env, delta))
        self.assertEqual((op['action'], op['phase']), ('resize', 'RESIZE'))
        self.assertEqual(self.store.get('Q#GLOBAL')['reserved_milliusd'], reserved + delta)
        self.assertEqual(self.store.get(env['pk'])['status'], 'RESIZING')
        driver = FakeDriver(); current = self.store.get(env['pk']); op = self.store.get(op['pk'])
        for _ in range(3):
            if resize.step(driver, current, op):
                break
        self.assertEqual(driver.ready_calls, 1)
        update = driver.cloudformation.updates[0]
        sent = json.loads(update['TemplateBody'])
        self.assertEqual(sent['Resources']['Instance']['Properties']['InstanceType'], 't3.small')
        self.assertEqual(sent['Resources']['DataVolume'], driver.cloudformation.template['Resources']['DataVolume'])
        self.assertEqual(sent['Resources']['DataVolume']['Properties']['SnapshotId'], 'snap-keep')
        self.assertEqual(update['Parameters'], [{'ParameterKey': 'A', 'UsePreviousValue': True}])
        self.assertTrue(update['ClientRequestToken'].startswith(op['operation_id']))

    def test_rollback_is_reported_and_spend_guard_blocks_upsizing(self):
        env = self.ready(); self.verify_small()
        delta = resize.targets(self.service, 'alice', env['environment_id'])['targets'][0]['delta_milliusd']
        spend_guard.set_state(self.service, 'admin', {'frozen': True, 'reason': 'Actual cost over budget'}, self.now)
        with self.assertRaises(HubError) as error:
            resize.begin(self.service, 'alice', env['environment_id'], 'resize-frozen', self.body(env, delta))
        self.assertEqual(error.exception.code, 'SPEND_GUARD_ACTIVE')
        driver = FakeDriver('UPDATE_ROLLBACK_COMPLETE')
        op = {'operation_id': 'op-x', 'resize_step': 'UPDATE_STACK', 'resize_target': SMALL}
        resize.step(driver, env, op)
        with self.assertRaises(HubError) as error:
            resize.step(driver, env, op)
        self.assertEqual(error.exception.code, 'RESIZE_ROLLED_BACK')


class MultiAzTests(unittest.TestCase):
    def test_ha_profile_is_published_but_closed_until_proven(self):
        for tid in ('T03', 'T04'):
            ha = next(p for p in configuration_profiles(tid) if p['id'] == 'ha')
            self.assertTrue(ha['configuration']['db_multi_az'])
            self.assertEqual(resolve_configuration(tid, ha['configuration']), ha['configuration'])
        from cloudhub.catalog import catalog
        row = next(r for r in catalog({'T03'}) if r['template_id'] == 'T03')
        self.assertFalse(next(p for p in row['configuration_options'] if p['id'] == 'ha')['create_enabled'])

    def test_estimate_bills_standby_instance_and_storage(self):
        rates = deepcopy(RATES)
        for key in ('rds_hour', 'rds_gib_month', 'rds_snapshot_gib_month', 'secret_month', 'secret_requests_10000'):
            rates['units'].setdefault(key, '0.02')
        e = Estimator(rates)
        base = configuration_profiles('T03')[0]['configuration']
        ha = next(p for p in configuration_profiles('T03') if p['id'] == 'ha')['configuration']
        one, two = e.estimate('T03', 2, configuration=base), e.estimate('T03', 2, configuration=ha)
        from decimal import Decimal
        self.assertEqual(Decimal(two['lines']['database']), 2 * Decimal(one['lines']['database']))
        self.assertEqual(Decimal(two['lines']['db_storage']), 2 * Decimal(one['lines']['db_storage']))
        self.assertEqual(two['lines']['compute'], one['lines']['compute'])

    def test_rds_template_sets_multi_az_only_for_ha(self):
        from cloudhub.rds_template import rds_template
        settings = {'vpc_id': 'vpc-1', 'db_subnet_ids': ['a', 'b'], 'public_subnet_ids': ['c', 'd'], 'postgres_version': '16.4',
                    'ami_id': 'ami-1', 'region': 'ap-southeast-1', 'availability_zone': 'az', 'instance_profile': 'p',
                    'public_subnet_id': 'c', 'ssh_cidr': '203.0.113.0/32', 'permissions_boundary': 'arn:aws:iam::1:policy/b'}
        def multi(cfg_id):
            cfg = next(p for p in configuration_profiles('T03') if p['id'] == cfg_id)['configuration']
            env = {'environment_id': 'env-' + 'a' * 24, 'owner_id': 'alice', 'template_id': 'T03', 'configuration': cfg}
            template = rds_template(env, settings)
            return template['Resources']['Database']['Properties']['MultiAZ']
        self.assertIs(multi('standard'), False)
        self.assertIs(multi('ha'), True)

    def test_larger_machine_needs_its_own_reviewed_rate(self):
        rates = deepcopy(RATES)
        e = Estimator(rates)
        self.assertFalse(e.estimate('T05', 1, configuration=SMALL)['approved'])
        rates['units']['ec2_hour.t3.small'] = '0.0208'
        self.assertTrue(Estimator(rates).estimate('T05', 1, configuration=SMALL)['approved'])


@only_own_tests
class CostSeriesTests(FeatureBase):
    def test_days_without_actuals_stay_null_and_estimate_follows_running_hours(self):
        env = self.ready(); self.now = env['created_at'] + 30 * 3600
        current = self.store.get(env['pk'])
        day = series(self.service, 'alice', env['environment_id'])['days'][0]['date']
        current['cost_report'] = {'status': 'PROVISIONAL', 'checked_at': self.now, 'days': [{'date': day, 'milliusd': 120, 'estimated': True}]}
        self.store.commit([current], {current['pk']: current['version']})
        result = series(self.service, 'alice', env['environment_id'])
        self.assertEqual(result['days'][0]['actual_milliusd'], 120)
        self.assertTrue(result['days'][0]['actual_is_estimated_by_aws'])
        self.assertTrue(all(d['actual_milliusd'] is None for d in result['days'][1:]))
        self.assertEqual(result['actual_total_milliusd'], 120)
        self.assertAlmostEqual(sum(d['running_hours'] for d in result['days']), 30, delta=0.6)
        with self.assertRaises(HubError):
            series(self.service, 'mallory', env['environment_id'])


class InfrastructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from generate_infra import build_template
        cls.r = build_template()['Resources']

    def test_terminal_iam_is_tag_scoped_and_routes_exist(self):
        statements = [s for p in self.r['ApiFunction']['Properties']['Policies'] if isinstance(p, dict) for s in p.get('Statement', [])]
        start = [s for s in statements if s['Action'] == 'ssm:StartSession']
        self.assertTrue(any(s.get('Condition') == {'StringEquals': {'ssm:resourceTag/cloudhub:managed': 'true'}} for s in start))
        self.assertTrue(all('instance/*' in json.dumps(s['Resource']) or 'SSM-SessionManagerRunShell' in json.dumps(s['Resource']) for s in start))
        paths = {(e['Properties']['Method'], e['Properties']['Path']) for e in self.r['ApiFunction']['Properties']['Events'].values()}
        self.assertIn(('POST', '/environments/{environment_id}/terminal/{session_id}'), paths)
        self.assertIn(('GET', '/environments/{environment_id}/{feature}'), paths)

    def test_resize_permissions_are_limited_to_managed_instances(self):
        doc = self.r['EnvironmentResizePolicy']['Properties']['PolicyDocument']['Statement'][0]
        self.assertEqual(doc['Condition']['StringEquals']['ec2:ResourceTag/cloudhub:managed'], 'true')
        worker = json.dumps(self.r['WorkerFunction']['Properties']['Policies'])
        self.assertIn('cloudformation:GetTemplate', worker)


if __name__ == '__main__':
    unittest.main()
