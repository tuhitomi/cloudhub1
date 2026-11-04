"""Cognito email templates with an ASCII transport and accented HTML content.

Subjects are plain text (HTML entities do not work there). The default sender
cannot be made multilingual per request by this static template; use an English
subject and a Vietnamese/English body without adding a sender service/trigger.
"""
from html import escape


def _html_text(value):
    return escape(value).encode('ascii', 'xmlcharrefreplace').decode('ascii')


def verification_template():
    """Keep the Cognito placeholder literal; never insert/log a real code."""
    return {
        'DefaultEmailOption': 'CONFIRM_WITH_CODE',
        'EmailSubject': 'CloudHub - Verification code',
        'EmailMessage': (
            '<div lang="vi"><p>'
            + _html_text('Mã xác thực CloudHub của bạn là:')
            + '</p><p><strong>{####}</strong></p><p>'
            + _html_text('Nhập mã này trên CloudHub để tiếp tục. Nếu bạn không yêu cầu mã, hãy bỏ qua email này.')
            + '</p></div><div lang="en"><p>'
            'Enter this verification code on CloudHub to continue. '
            'If you did not request a code, ignore this email.</p></div>'
        ),
    }


def patch_template(template):
    """Patch only the existing pool's verification message, preserving native IaC."""
    from copy import deepcopy
    result = deepcopy(template)
    resource = result['Resources']['UserPool']
    if resource['Type'] != 'AWS::Cognito::UserPool':
        raise ValueError('UserPool is not an existing Cognito pool')
    previous = resource['Properties'].get('VerificationMessageTemplate', {})
    if previous.get('DefaultEmailOption', 'CONFIRM_WITH_CODE') != 'CONFIRM_WITH_CODE':
        raise ValueError('Link-based verification requires a separate reviewed change')
    resource['Properties']['VerificationMessageTemplate'] = {
        **previous, **verification_template(),
    }
    return result


def validate_changes(detail):
    """An email repair must never modify IAM, identity IDs or another resource."""
    if detail.get('Status') != 'CREATE_COMPLETE' or detail.get('ExecutionStatus') != 'AVAILABLE':
        raise ValueError('Changeset is not ready')
    changes = detail.get('Changes', [])
    if len(changes) != 1:
        raise ValueError('Expected exactly one UserPool modification')
    change = changes[0]['ResourceChange']
    if (change.get('LogicalResourceId') != 'UserPool'
            or change.get('ResourceType') != 'AWS::Cognito::UserPool'
            or change.get('Action') != 'Modify'
            or change.get('Replacement') != 'False'):
        raise ValueError('Change exceeds verification-email repair scope')
    details = change.get('Details', [])
    if not details or any(d.get('Target', {}).get('Attribute') != 'Properties'
           or d.get('Target', {}).get('Name') != 'VerificationMessageTemplate'
           for d in details):
        raise ValueError('Unexpected UserPool property modification')
