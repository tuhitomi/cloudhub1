"""LOCAL only: spend guard, tracing, WAF and change-set role templates."""
import json, sys, unittest
from pathlib import Path
from types import SimpleNamespace
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
sys.path.insert(0, str(ROOT / 'scripts'))
from cloudhub import spend_guard
from cloudhub.errors import HubError
from cloudhub.store import MemoryStore
import test_lifecycle
LifecycleTests = test_lifecycle.LifecycleTests

ACTUAL = ('AWS Budget Notification November 12, 2026\nAWS Account 123456789012\n\nDear AWS Customer,\n\n'
          'You requested that we alert you when the ACTUAL Cost associated with your cloudhub-monthly budget is '
          'greater than 100% of $50.00 for the current month. The ACTUAL Cost associated with this budget is $51.20. '
          'You can find additional details below and by accessing the AWS Budgets dashboard.')
FORECAST = ACTUAL.replace('ACTUAL', 'FORECASTED')
WARNING = ACTUAL.replace('100%', '80%').replace('$51.20', '$40.10')


def sns(message):
    return {'Records': [{'Sns': {'Message': message}}]}


class ParseTests(unittest.TestCase):
    def test_actual_notification_fields(self):
        self.assertEqual(spend_guard.parse(ACTUAL), {'kind': 'ACTUAL', 'budget_name': 'cloudhub-monthly',
            'threshold_percent': 100.0, 'limit_usd': 50.0, 'actual_usd': 51.2})

    def test_unrelated_messages_are_ignored(self):
        self.assertIsNone(spend_guard.parse('{"AlarmName":"x"}'))
        self.assertIsNone(spend_guard.parse(''))


class HandlerTests(unittest.TestCase):
    def setUp(self):
        self.service = SimpleNamespace(store=MemoryStore())
        self.sent = []
        self.publish = lambda subject, text: self.sent.append(subject)

    def run_handler(self, message):
        return spend_guard.sns_handler(sns(message), service=self.service, publish=self.publish)['results']

    def test_actual_at_threshold_freezes_once_and_alerts_once(self):
        self.assertEqual(self.run_handler(ACTUAL), ['FROZEN'])
        self.assertEqual(self.run_handler(ACTUAL), ['FROZEN'])
        row = spend_guard.active(self.service)
        self.assertEqual((row['source'], row['actual_usd'], row['limit_usd']), ('AWS_BUDGETS', 51.2, 50.0))
        self.assertEqual([h['action'] for h in row['history']], ['NOTIFIED', 'FROZEN'])
        self.assertEqual(self.sent, ['CloudHub spend guard frozen'])

    def test_forecast_and_lower_threshold_only_warn(self):
        self.assertEqual(self.run_handler(FORECAST), ['BELOW_THRESHOLD_OR_FORECAST'])
        self.assertEqual(self.run_handler(WARNING), ['BELOW_THRESHOLD_OR_FORECAST'])
        self.assertIsNone(spend_guard.active(self.service))

    def test_other_budget_name_is_ignored(self):
        notice = spend_guard.parse(ACTUAL)
        self.assertIsNone(spend_guard.freeze_from_budget(self.service, notice, 1, budget_name='other-monthly'))
        self.assertIsNone(spend_guard.active(self.service))

    def test_admin_release_requires_reason_and_is_audited(self):
        self.run_handler(ACTUAL)
        with self.assertRaises(HubError):
            spend_guard.set_state(self.service, 'admin', {'frozen': False}, 2)
        with self.assertRaises(HubError):
            spend_guard.set_state(self.service, 'admin', {'frozen': False, 'reason': 'short'}, 2)
        view = spend_guard.set_state(self.service, 'admin', {'frozen': False, 'reason': 'Billing reviewed, budget raised'}, 2)
        self.assertFalse(view['frozen'])
        self.assertEqual(view['history'][0], {'at': 2, 'action': 'RELEASED', 'by': 'admin', 'reason': 'Billing reviewed, budget raised'})
        self.assertIsNone(spend_guard.active(self.service))


class EnforcementTests(test_lifecycle.LifecycleTests):
    """Reuse the lifecycle fixture; only the spend guard tests run from this class."""
    def freeze(self):
        spend_guard.set_state(self.service, 'admin', {'frozen': True, 'reason': 'Actual cost over budget'}, self.now)

    def test_create_is_refused_while_frozen_and_allowed_after_release(self):
        self.freeze()
        with self.assertRaises(HubError) as error:
            self.service.create('alice', 'create-while-frozen', {'template_id': 'T05', 'estimate_hours': 1, 'operating_policy': self.policy()})
        self.assertEqual(error.exception.code, 'SPEND_GUARD_ACTIVE')
        self.assertEqual(error.exception.details['budget_scope'], 'AWS_SPEND_GUARD')
        self.assertIsNone(self.store.get('Q#alice'))
        spend_guard.set_state(self.service, 'admin', {'frozen': False, 'reason': 'Billing reviewed and accepted'}, self.now)
        self.assertEqual(self.service.create('alice', 'create-after-release', {'template_id': 'T05', 'estimate_hours': 1,
                                             'operating_policy': self.policy()})['status'], 'QUEUED')

    def test_auto_renew_is_blocked_and_confirmed_ending_policy_runs(self):
        env = self.ready(self.policy('AUTO_RENEW'))
        self.freeze()
        self.now = env['deadline']
        op = self.service.expire(env['environment_id'])
        self.assertEqual(op['action'], 'pause')
        self.finish(op)
        ended = self.store.get(env['pk'])
        self.assertEqual(ended['status'], 'PAUSED')
        self.assertEqual(ended['renewal_blocked_reason']['code'], 'SPEND_GUARD_ACTIVE')

    def test_manual_renewal_is_refused_but_end_still_works(self):
        env = self.ready()
        self.freeze()
        with self.assertRaises(HubError) as error:
            self.service.renew('alice', env['environment_id'], 'renew-while-frozen',
                               {'minutes': 5, 'confirmed': True, 'expected_revision': env['lifecycle_revision']})
        self.assertEqual(error.exception.code, 'SPEND_GUARD_ACTIVE')
        self.assertEqual(self.store.get(env['pk'])['renewal_count'], 0)


# Do not rerun every inherited lifecycle test from this module.
del LifecycleTests
for name in [n for n in dir(test_lifecycle.LifecycleTests) if n.startswith('test_')]:
    if getattr(EnforcementTests, name) is getattr(test_lifecycle.LifecycleTests, name):
        setattr(EnforcementTests, name, None)


class InfrastructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from generate_infra import build_template
        cls.template = build_template()
        cls.r = cls.template['Resources']

    def test_budget_feeds_guard_only_when_enabled(self):
        self.assertEqual(self.template['Parameters']['MonthlyBudgetUsd']['Default'], 0)
        for name in ('SpendGuardTopic', 'SpendGuardTopicPolicy', 'MonthlyBudget', 'SpendGuardFunction'):
            self.assertEqual(self.r[name]['Condition'], 'HasSpendBudget')
        budget = self.r['MonthlyBudget']['Properties']
        kinds = [(n['Notification']['NotificationType'], n['Notification']['Threshold']) for n in budget['NotificationsWithSubscribers']]
        self.assertIn(('ACTUAL', {'Ref': 'SpendGuardThresholdPercent'}), kinds)
        self.assertIn(('FORECASTED', 100), kinds)
        self.assertNotIn('KmsMasterKeyId', self.r['SpendGuardTopic'].get('Properties', {}))
        statement = self.r['SpendGuardTopicPolicy']['Properties']['PolicyDocument']['Statement'][0]
        self.assertEqual(statement['Principal'], {'Service': 'budgets.amazonaws.com'})

    def test_guard_function_can_only_touch_its_own_row(self):
        statements = self.r['SpendGuardFunction']['Properties']['Policies'][0]['Statement']
        table = next(s for s in statements if 'dynamodb:PutItem' in s['Action'])
        self.assertEqual(table['Condition'], {'ForAllValues:StringEquals': {'dynamodb:LeadingKeys': ['G#SPEND_GUARD']}})
        self.assertNotIn('dynamodb:DeleteItem', table['Action'])

    def test_every_function_and_the_state_machine_are_traced(self):
        functions = [r for r in self.r.values() if r['Type'] == 'AWS::Serverless::Function']
        self.assertGreaterEqual(len(functions), 5)
        for resource in functions:
            self.assertEqual(resource['Properties']['Tracing'], 'Active')
        self.assertEqual(self.r['StateMachine']['Properties']['Tracing'], {'Enabled': True})

    def test_identity_waf_is_optional_and_attached_to_user_pool(self):
        acl = self.r['IdentityWebAcl']
        self.assertEqual((acl['Condition'], acl['Properties']['Scope']), ('HasIdentityWaf', 'REGIONAL'))
        rate = next(rule for rule in acl['Properties']['Rules'] if 'RateBasedStatement' in rule['Statement'])
        self.assertEqual(rate['Statement']['RateBasedStatement']['AggregateKeyType'], 'IP')
        self.assertEqual(self.r['IdentityWebAclAssociation']['Properties']['ResourceArn'], {'Fn::GetAtt': ['UserPool', 'Arn']})

    def test_admin_spend_guard_routes_exist(self):
        paths = {(e['Properties']['Method'], e['Properties']['Path']) for e in self.r['ApiFunction']['Properties']['Events'].values()}
        self.assertTrue({('GET', '/admin/spend-guard'), ('POST', '/admin/spend-guard')} <= paths)


class EdgeAndCiTests(unittest.TestCase):
    def test_edge_waf_is_us_east_1_cloudfront_scope(self):
        from edge_waf import template
        t = template()
        self.assertEqual(t['Resources']['FrontendWebAcl']['Properties']['Scope'], 'CLOUDFRONT')
        self.assertIn('us-east-1', json.dumps(t['Rules']))
        committed = json.loads((ROOT / 'infra/hosting/edge-waf.example.json').read_text(encoding='utf-8'))
        self.assertEqual(committed, t)

    def test_edge_stack_attaches_optional_web_acl(self):
        edge = json.loads((ROOT / 'infra/hosting/edge-domain.example.json').read_text(encoding='utf-8'))
        config = edge['Resources']['FrontendDistribution']['Properties']['DistributionConfig']
        self.assertEqual(config['WebACLId'], {'Fn::If': ['HasFrontendWebAcl', {'Ref': 'FrontendWebAclArn'}, {'Ref': 'AWS::NoValue'}]})
        self.assertEqual(edge['Parameters']['FrontendWebAclArn']['Default'], '')

    def test_ci_role_can_propose_but_never_execute(self):
        from ci_deploy_role import template
        role = template()['Resources']['ChangeSetRole']['Properties']
        trust = role['AssumeRolePolicyDocument']['Statement'][0]['Condition']['StringEquals']
        self.assertTrue(any(key.endswith(':sub') for key in trust))
        statements = role['Policies'][0]['PolicyDocument']['Statement']
        allowed = {a for s in statements if s['Effect'] == 'Allow' for a in ([s['Action']] if isinstance(s['Action'], str) else s['Action'])}
        denied = next(s for s in statements if s['Effect'] == 'Deny')['Action']
        self.assertIn('cloudformation:CreateChangeSet', allowed)
        self.assertNotIn('cloudformation:ExecuteChangeSet', allowed)
        self.assertIn('cloudformation:ExecuteChangeSet', denied)
        self.assertIn('iam:PassRole', denied)

    def test_changeset_workflow_is_manual_main_only_and_keyless(self):
        text = (ROOT / '.github/workflows/changeset.yml').read_text(encoding='utf-8')
        self.assertIn('workflow_dispatch', text)
        self.assertNotIn('push:', text)
        self.assertIn("github.ref == 'refs/heads/main'", text)
        self.assertIn('id-token: write', text)
        self.assertIn('--no-execute-changeset', text)
        self.assertNotIn('AWS_SECRET_ACCESS_KEY', text)


if __name__ == '__main__':
    unittest.main()
