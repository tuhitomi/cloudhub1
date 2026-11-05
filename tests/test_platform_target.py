import copy
import hashlib
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from prepare_platform_target import ACTIVE_TEMPLATES, CLOSED, RATE_REQUIREMENTS, plan, prepare


class PlatformTargetTests(unittest.TestCase):
    def config(self, region='ap-northeast-1'):
        return {'schema': 1, 'account_id': '123456789012', 'region': region, 'profile': 'approved-test-profile',
                'stack_name': 'cloudhub-portability-test', 'regional_inputs': {
                    'VpcId': 'vpc-12345678', 'PublicSubnetId': 'subnet-11111111',
                    'PublicSubnet2Id': 'subnet-22222222', 'DbSubnet1Id': 'subnet-33333333',
                    'DbSubnet2Id': 'subnet-44444444', 'AvailabilityZone': region + 'a',
                    'AmiId': 'ami-12345678', 'SshCidr': '192.0.2.1/32', 'PostgresVersion': '16.3',
                    'ApprovedImage': '123456789012.dkr.ecr.' + region + '.amazonaws.com/cloudhub-test@sha256:' + 'a' * 64},
                'budget_usd': '1.234', 'cash_budget_usd': 0, 'approval_reference': 'LOCAL_FIXTURE_NOT_AUTHORIZATION',
                'prices_file': None}

    def prices(self, region='ap-northeast-1'):
        return {'approved': True, 'region': region, 'updated_at': '2026-10-21',
                'source_urls': ['LOCAL_FIXTURE_NOT_AWS_PRICE_EVIDENCE'],
                'units': {key: '0.1' for tid in ACTIVE_TEMPLATES for key in RATE_REQUIREMENTS[tid]},
                'configuration_verifications': {'DO_NOT_COPY_PROOF': {'passed': True}}}

    def test_three_regions_have_closed_gates_without_claiming_aws(self):
        for region in ('ap-southeast-1', 'ap-northeast-1', 'us-east-1'):
            with self.subTest(region=region):
                report = plan(self.config(region), self.prices(region))
                self.assertTrue(report['local_inputs_complete'])
                self.assertFalse(report['aws_verified'])
                self.assertFalse(report['production_cutover_allowed'])
                params = {r['ParameterKey']: r['ParameterValue'] for r in report['parameters_for_review']}
                self.assertTrue(all(params[k] == 'false' for k in CLOSED))
                self.assertEqual(params['VerifiedTemplates'], '')
                self.assertEqual(params['ValidationTemplates'], '')
                self.assertNotIn('DO_NOT_COPY_PROOF', params['PricesJson'])
                self.assertNotIn('UiEdgeSecret', params)

    def test_unknown_regions_and_zone_forms_do_not_get_opened(self):
        for region in ('eu-west-1', 'cn-north-1', 'us-gov-west-1', 'us-east-1-wl1'):
            with self.subTest(region=region), self.assertRaises(ValueError):
                plan(self.config(region), self.prices(region))
        config = self.config()
        config['regional_inputs']['AvailabilityZone'] = 'ap-northeast-1-tpe-1a'
        self.assertIn('Missing/invalid target AvailabilityZone', plan(config, self.prices())['configuration_blockers'])

    def test_cross_region_image_unapproved_price_and_duplicate_subnets_block(self):
        config = self.config()
        config['regional_inputs']['ApprovedImage'] = self.config('ap-southeast-1')['regional_inputs']['ApprovedImage']
        config['regional_inputs']['DbSubnet1Id'] = config['regional_inputs']['PublicSubnetId']
        report = plan(config, self.prices('us-east-1'))
        self.assertFalse(report['local_inputs_complete'])
        self.assertTrue(any('ECR' in b for b in report['configuration_blockers']))
        self.assertTrue(any('distinct' in b for b in report['configuration_blockers']))
        self.assertTrue(any('price' in b for b in report['configuration_blockers']))

    def test_invalid_cap_or_public_ssh_or_secret_overrides_are_rejected(self):
        for amount in ('NaN', '-1', '1.2345', None):
            config = self.config()
            config['budget_usd'] = amount
            self.assertFalse(plan(config, self.prices())['local_inputs_complete'])
        config = self.config()
        config['regional_inputs']['SshCidr'] = '0.0.0.0/0'
        self.assertFalse(plan(config, self.prices())['local_inputs_complete'])
        for field in ('aws_secret_access_key', 'UiEdgeSecret', 'ContinuousEnabled'):
            config = self.config()
            config[field] = 'MUST_NOT_BE_SERIALIZED'
            with self.assertRaises(ValueError):
                plan(config, self.prices())

    def test_packaged_code_and_workflow_resolve_without_production_config(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'packet'
            before = (ROOT / 'infra/control-plane.json').read_bytes()
            report = prepare(self.config(), target, self.prices())
            template = json.loads((target / 'infra/control-plane.json').read_text(encoding='utf-8'))
            for name in ('ApiFunction', 'WorkerFunction', 'SweepFunction', 'ExpiryFunction'):
                code = target / 'infra' / template['Resources'][name]['Properties']['CodeUri']
                self.assertTrue((code / 'cloudhub/service.py').is_file())
            workflow = target / 'infra' / template['Resources']['StateMachine']['Properties']['DefinitionUri']
            self.assertTrue(workflow.is_file())
            self.assertFalse((target / 'frontend/config.js').exists())
            self.assertEqual(before, (ROOT / 'infra/control-plane.json').read_bytes())
            self.assertEqual(report['aws_mutations'], 0)
            manifest = json.loads((target / 'manifest.json').read_text(encoding='utf-8'))
            for name, sha in manifest['files'].items():
                self.assertEqual(sha, hashlib.sha256((target / name).read_bytes()).hexdigest())
            # Execute the handed-off scripts from the packet, with synthetic
            # outputs only. No DNS/API requests or real authentication occur.
            outputs = Path(directory) / 'offline-stack-outputs.json'
            public_config = Path(directory) / 'offline-public.json'
            public_dir = Path(directory) / 'offline-public-assets'
            values = {'ApiUrl': 'https://api123.execute-api.ap-northeast-1.amazonaws.com',
                      'ClientId': 'offlineclient123', 'CognitoDomain': 'https://cloudhub-offline.auth.ap-northeast-1.amazoncognito.com',
                      'FrontendUrl': 'https://offline-test.cloudfront.net/', 'Region': 'ap-northeast-1'}
            outputs.write_text(json.dumps({'Stacks': [{'StackStatus': 'CREATE_COMPLETE', 'Outputs': [
                {'OutputKey': key, 'OutputValue': value} for key, value in values.items()]}]}), encoding='utf-8')
            subprocess.run([sys.executable, '-B', str(target / 'scripts/configure_frontend.py'),
                            str(outputs), '--out-json', str(public_config)], check=True, capture_output=True)
            subprocess.run([sys.executable, '-B', str(target / 'scripts/build_pages_live.py'),
                            '--config', str(public_config), '--out', str(public_dir)], check=True, capture_output=True)
            self.assertTrue((public_dir / 'workspace-ui.js').is_file())
            self.assertIn('api123.execute-api.ap-northeast-1', (public_dir / 'config.js').read_text(encoding='utf-8'))
            self.assertNotIn('cloudhub1.me', (public_dir / 'config.js').read_text(encoding='utf-8'))
            with self.assertRaises(ValueError):
                prepare(self.config(), target, self.prices())

    def test_source_folders_cannot_be_used_as_output(self):
        for destination in (ROOT, ROOT.parent, ROOT / 'frontend/packet', ROOT / 'infra/packet'):
            with self.subTest(destination=destination), self.assertRaises(ValueError):
                prepare(self.config(), destination, self.prices())

    def test_example_stays_draft_with_unknown_budget_and_prices(self):
        example = json.loads((ROOT / 'config/platform-target.example.json').read_text(encoding='utf-8'))
        original = copy.deepcopy(example)
        report = plan(example)
        self.assertFalse(report['local_inputs_complete'])
        self.assertGreater(len(report['configuration_blockers']), 5)
        self.assertEqual(original, example)


if __name__ == '__main__':
    unittest.main()
