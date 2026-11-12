"""Browser terminal (Session Manager), EC2 resize and daily cost series."""


def extend(doc):
    schemas = doc['components']['schemas']
    ref = lambda name: {'$ref': '#/components/schemas/' + name}
    env_param = {'in': 'path', 'name': 'environment_id', 'required': True, 'schema': {'type': 'string', 'pattern': '^env-[a-f0-9]{24}$'}}
    security = [{'CognitoAccessToken': []}]
    errors = {str(c): {'description': d} for c, d in [(400, 'Invalid input'), (401, 'Cognito JWT required'), (404, 'Not owned'), (409, 'State, verification, price or quota conflict')]}
    milli = {'type': 'integer', 'nullable': True}
    schemas.update({
        'TerminalStart': {'type': 'object', 'additionalProperties': False, 'properties': {'node': {'type': 'integer', 'minimum': 0, 'maximum': 1}}},
        'TerminalSession': {'type': 'object', 'required': ['session_id', 'stream_url', 'token'], 'properties': {
            'session_id': {'type': 'string'}, 'stream_url': {'type': 'string', 'pattern': '^wss://ssmmessages\\.'},
            'token': {'type': 'string', 'description': 'One-time Session Manager token for this browser only; never stored by CloudHub.'},
            'instance_index': {'type': 'integer'}, 'region': {'type': 'string'}, 'started_at': {'type': 'integer'}}},
        'TerminalEnd': {'type': 'object', 'required': ['session_id', 'status'], 'properties': {
            'session_id': {'type': 'string'}, 'status': {'type': 'string', 'enum': ['ACTIVE', 'ENDED']}, 'ended_at': {'type': 'integer', 'nullable': True}}},
        'ResizeOptions': {'type': 'object', 'required': ['environment_id', 'supported', 'targets'], 'properties': {
            'environment_id': {'type': 'string'}, 'supported': {'type': 'boolean'}, 'current_instance_type': {'type': 'string'},
            'interruption': {'type': 'string'}, 'targets': {'type': 'array', 'items': {'type': 'object', 'properties': {
                'configuration_id': {'type': 'string'}, 'instance_type': {'type': 'string'}, 'label': {'type': 'string'},
                'verified': {'type': 'boolean'}, 'delta_milliusd': milli, 'remaining_hours': {'type': 'string'}, 'prices_available': {'type': 'boolean'}}}}}},
        'ResizeInput': {'type': 'object', 'additionalProperties': False,
            'required': ['configuration_id', 'expected_revision', 'expected_delta_milliusd', 'confirmed'], 'properties': {
                'configuration_id': {'type': 'string'}, 'expected_revision': {'type': 'integer'},
                'expected_delta_milliusd': {'type': 'integer', 'description': 'Exact value from GET .../resize; acts as the quote fingerprint.'},
                'confirmed': {'type': 'boolean', 'enum': [True]}}},
        'CostSeries': {'type': 'object', 'required': ['environment_id', 'days'], 'properties': {
            'environment_id': {'type': 'string'}, 'currency': {'type': 'string', 'enum': ['USD']}, 'hourly_estimate_milliusd': milli,
            'report_status': {'type': 'string'}, 'estimated_total_milliusd': milli, 'actual_total_milliusd': milli, 'difference_milliusd': milli,
            'assumptions': {'type': 'array', 'items': {'type': 'string'}},
            'days': {'type': 'array', 'maxItems': 62, 'items': {'type': 'object', 'properties': {
                'date': {'type': 'string', 'format': 'date'}, 'running_hours': {'type': 'number'}, 'estimated_milliusd': milli,
                'actual_milliusd': {**milli, 'description': 'null means no Cost Explorer data for that day, never zero.'},
                'actual_is_estimated_by_aws': {'type': 'boolean'}}}}}},
    })
    body = lambda name: {'required': True, 'content': {'application/json': {'schema': ref(name)}}}
    ok = lambda code, name, text: {code: {'description': text, 'content': {'application/json': {'schema': ref(name)}}}, **errors}
    doc['paths']['/environments/{environment_id}/terminal'] = {
        'post': {'operationId': 'startTerminal', 'summary': 'Start a Session Manager shell on the owned T01/T05/T08 instance.',
                 'description': 'No SSH key or inbound port. IAM allows only CloudHub-managed instances. At most 2 active sessions per environment.',
                 'security': security, 'parameters': [env_param], 'requestBody': body('TerminalStart'), 'responses': ok('201', 'TerminalSession', 'Session started')},
        'get': {'operationId': 'listTerminals', 'summary': 'Active terminal sessions of the environment (no tokens).', 'security': security,
                'parameters': [env_param], 'responses': {'200': {'description': 'Sessions'}, **errors}}}
    doc['paths']['/environments/{environment_id}/terminal/{session_id}'] = {
        'post': {'operationId': 'endTerminal', 'summary': 'Terminate an owned terminal session.', 'security': security,
                 'parameters': [env_param, {'in': 'path', 'name': 'session_id', 'required': True, 'schema': {'type': 'string', 'maxLength': 96}}],
                 'responses': ok('200', 'TerminalEnd', 'Session ended')}}
    doc['paths']['/environments/{environment_id}/resize'] = {
        'get': {'operationId': 'resizeOptions', 'summary': 'Machine types reachable without changing disks, with verification and cost difference.',
                'security': security, 'parameters': [env_param], 'responses': ok('200', 'ResizeOptions', 'Options')},
        'post': {'operationId': 'resizeEnvironment', 'summary': 'Change the EC2 instance type through the environment CloudFormation stack.',
                 'description': 'EC2 stop/start; instance ID, disks and data are kept; public IPv4 may change. Failed updates roll back to the previous type.',
                 'security': security, 'parameters': [env_param, {'in': 'header', 'name': 'Idempotency-Key', 'required': True, 'schema': {'type': 'string'}}],
                 'requestBody': body('ResizeInput'), 'responses': ok('202', 'Operation', 'Resize accepted')}}
    doc['paths']['/environments/{environment_id}/cost-series'] = {
        'get': {'operationId': 'costSeries', 'summary': 'Daily estimate next to the last reconciled Cost Explorer actuals.',
                'security': security, 'parameters': [env_param], 'responses': ok('200', 'CostSeries', 'Series')}}
