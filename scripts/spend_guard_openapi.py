"""Administrator view and release of the AWS spend guard."""


def extend(doc):
    schemas = doc['components']['schemas']
    number = {'type': 'number', 'nullable': True}
    schemas['SpendGuard'] = {'type': 'object', 'required': ['frozen', 'history'], 'properties': {
        'frozen': {'type': 'boolean', 'description': 'True blocks create, restore, renew and resume; end, backup and export stay available.'},
        'source': {'type': 'string', 'nullable': True, 'enum': ['AWS_BUDGETS', 'ADMIN', None]},
        'changed_at': {'type': 'integer', 'nullable': True}, 'changed_by': {'type': 'string', 'nullable': True},
        'reason': {'type': 'string', 'nullable': True}, 'budget_name': {'type': 'string', 'nullable': True},
        'threshold_percent': number, 'actual_usd': number, 'limit_usd': number,
        'history': {'type': 'array', 'maxItems': 20, 'items': {'type': 'object', 'additionalProperties': True}}}}
    schemas['SpendGuardInput'] = {'type': 'object', 'additionalProperties': False, 'required': ['frozen', 'reason'], 'properties': {
        'frozen': {'type': 'boolean'}, 'reason': {'type': 'string', 'minLength': 10, 'maxLength': 500}}}
    ref = lambda name: {'$ref': '#/components/schemas/' + name}
    errors = {str(code): {'description': text} for code, text in [(400, 'Invalid input'), (401, 'Cognito JWT required'), (403, 'Administrator required')]}
    doc['paths']['/admin/spend-guard'] = {
        'get': {'operationId': 'getSpendGuard', 'summary': 'Read the AWS spend guard state and its last 20 changes.',
            'security': [{'CognitoAccessToken': []}],
            'responses': {'200': {'description': 'Current guard', 'content': {'application/json': {'schema': ref('SpendGuard')}}}, **errors}},
        'post': {'operationId': 'setSpendGuard', 'summary': 'Freeze or release the spend guard with an audited reason.',
            'description': 'AWS Budgets freezes the guard automatically when actual monthly cost crosses SpendGuardThresholdPercent. '
                           'It never releases itself; an administrator releases it after reviewing billing. '
                           'Independent of the internal forecast wallets and platform budget.',
            'security': [{'CognitoAccessToken': []}],
            'requestBody': {'required': True, 'content': {'application/json': {'schema': ref('SpendGuardInput')}}},
            'responses': {'200': {'description': 'Updated guard', 'content': {'application/json': {'schema': ref('SpendGuard')}}}, **errors}}}
