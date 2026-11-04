"""Encoding and native-template boundaries; no AWS calls or email delivery."""
import json
import sys
import unittest
from copy import deepcopy
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from cognito_messages import patch_template, validate_changes, verification_template


class CognitoMessageTests(unittest.TestCase):
    def test_ascii_transport_survives_legacy_windows_encoding_with_vietnamese_intact(self):
        template = verification_template()
        for value in template.values():
            self.assertTrue(value.isascii())
            self.assertEqual(value.encode('cp1252', errors='replace').decode('cp1252'), value)
        rendered = unescape(template['EmailMessage'])
        self.assertIn('Mã xác thực CloudHub của bạn là:', rendered)
        self.assertIn('Nếu bạn không yêu cầu mã, hãy bỏ qua email này.', rendered)
        self.assertNotIn('?', rendered)
        self.assertEqual(json.loads(json.dumps(template, ensure_ascii=True)), template)

    def test_code_is_substituted_once_without_changing_cognito_contract(self):
        template = verification_template()
        self.assertEqual(template['DefaultEmailOption'], 'CONFIRM_WITH_CODE')
        self.assertEqual(template['EmailMessage'].count('{####}'), 1)
        self.assertNotIn('{####}', template['EmailSubject'])
        self.assertLessEqual(len(template['EmailSubject']), 140)
        self.assertLessEqual(len(template['EmailMessage']), 20000)
        self.assertIn('lang="vi"', template['EmailMessage'])
        self.assertIn('lang="en"', template['EmailMessage'])
        self.assertNotIn('<script', template['EmailMessage'])

    def test_native_patch_preserves_every_other_resource_and_pool_setting(self):
        before = {'Parameters': {'keep': {}}, 'Resources': {
            'UserPool': {'Type': 'AWS::Cognito::UserPool', 'DeletionPolicy': 'Retain', 'Properties': {
                'Policies': {'PasswordPolicy': {'MinimumLength': 12}},
                'AdminCreateUserConfig': {'AllowAdminCreateUserOnly': False},
                'EmailConfiguration': {'EmailSendingAccount': 'COGNITO_DEFAULT'},
                'VerificationMessageTemplate': {'DefaultEmailOption': 'CONFIRM_WITH_CODE',
                    'EmailSubject': 'M? x?c th?c', 'EmailMessage': 'M? {####}.', 'SmsMessage': 'Code {####}'}}},
            'UserClient': {'Type': 'AWS::Cognito::UserPoolClient', 'Properties': {'ClientName': 'unchanged'}},
            'WorkerRole': {'Type': 'AWS::IAM::Role', 'Properties': {'unchanged': True}}}}
        saved = deepcopy(before)
        result = patch_template(before)
        self.assertEqual(before, saved)
        self.assertEqual(patch_template(result), result)
        expected = deepcopy(before)
        expected['Resources']['UserPool']['Properties']['VerificationMessageTemplate'].update(verification_template())
        self.assertEqual(result, expected)
        self.assertEqual(result['Resources']['UserPool']['Properties']['VerificationMessageTemplate']['SmsMessage'], 'Code {####}')

    def test_link_verification_is_not_silently_changed(self):
        source = {'Resources': {'UserPool': {'Type': 'AWS::Cognito::UserPool', 'Properties': {
            'VerificationMessageTemplate': {'DefaultEmailOption': 'CONFIRM_WITH_LINK'}}}}}
        with self.assertRaises(ValueError):
            patch_template(source)

    def test_iac_and_generator_share_the_safe_template(self):
        stored = json.loads((ROOT / 'infra/control-plane.json').read_text(encoding='utf-8'))
        from generate_infra import build_template
        for source in [stored, build_template()]:
            self.assertEqual(source['Resources']['UserPool']['Properties']['VerificationMessageTemplate'], verification_template())

    def test_changeset_rejects_replacement_other_resources_and_non_message_changes(self):
        row = {'LogicalResourceId': 'UserPool', 'ResourceType': 'AWS::Cognito::UserPool',
               'Action': 'Modify', 'Replacement': 'False', 'Details': [
                   {'Target': {'Attribute': 'Properties', 'Name': 'VerificationMessageTemplate'}}]}
        def detail(change):
            return {'Status': 'CREATE_COMPLETE', 'ExecutionStatus': 'AVAILABLE', 'Changes': [{'ResourceChange': change}]}
        validate_changes(detail(row))
        for key, value in [('LogicalResourceId', 'WorkerRole'), ('Action', 'Remove'), ('Replacement', 'True'),
                           ('Details', []),
                           ('Details', [{'Target': {'Attribute': 'Properties', 'Name': 'Policies'}}])]:
            bad = {**row, key: value}
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_changes(detail(bad))
        bad = detail(row)
        bad['Changes'].append({'ResourceChange': row})
        with self.assertRaises(ValueError):
            validate_changes(bad)


if __name__ == '__main__':
    unittest.main()
