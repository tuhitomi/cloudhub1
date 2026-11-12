"""Browser terminal through AWS Systems Manager Session Manager.

No SSH key, inbound port or bastion is involved. The API checks ownership and
state, then calls ssm:StartSession for the environment's own instance. The
returned StreamUrl and one-time TokenValue go straight to the owner's browser,
which speaks the Session Manager data-channel protocol (frontend/ssm-session.js)
over WebSocket to ssmmessages.<region>.amazonaws.com.

IAM limits the API role to instances tagged cloudhub:managed=true and to the
SSM-SessionManagerRunShell document. Session start and end are recorded per
owner; the token itself is never stored.
"""
import re

from .errors import HubError

SUPPORTED = {'T01', 'T05', 'T08'}
DOCUMENT = 'SSM-SessionManagerRunShell'
MAX_ACTIVE_PER_ENVIRONMENT = 2
SESSION_ID = re.compile(r'[A-Za-z0-9._@+=-]{1,96}')


def _instances(env):
    if env['template_id'] == 'T08':
        return list(env.get('node_ids') or [])
    return [env['instance_id']] if env.get('instance_id') else []


def _client(service, env, clients=None):
    if clients and 'ssm' in clients:
        return clients['ssm']
    import boto3
    from botocore.config import Config
    return boto3.client('ssm', region_name=service.region_for(env),
                        config=Config(connect_timeout=2, read_timeout=10, retries={'mode': 'standard', 'max_attempts': 2}))


def _record(service, env, owner, session_id, instance_id, now):
    from .service import record
    return record('terminal', session_id, owner, session_id=session_id, environment_id=env['environment_id'],
                  instance_id=instance_id, region=service.region_for(env), started_at=now, ended_at=None, status='ACTIVE')


STALE_SECONDS = 3600  # a tab closed without "end" still frees its slot after an hour


def active_sessions(service, owner, eid):
    cutoff = int(service.clock()) - STALE_SECONDS
    return [r for r in service.store.list_owner(owner, 'terminal')
            if r['environment_id'] == eid and r['status'] == 'ACTIVE' and r['started_at'] > cutoff]


def start(service, owner, eid, body, clients=None):
    if set(body or {}) - {'node'}:
        raise HubError('INVALID_INPUT', 'Chỉ chọn được số thứ tự máy (node).')
    env = service.owned('E', eid, owner)
    if env['template_id'] not in SUPPORTED:
        raise HubError('TERMINAL_UNSUPPORTED', 'Terminal chỉ có cho máy Linux (T01), website trên máy chủ (T05) và ổ đĩa dùng chung (T08).', 409)
    if env['status'] != 'READY':
        raise HubError('TERMINAL_UNAVAILABLE', 'Môi trường phải ở trạng thái sẵn sàng.', 409)
    instances = _instances(env)
    node = (body or {}).get('node', 0)
    if type(node) is not int or not 0 <= node < len(instances):
        raise HubError('INVALID_INPUT', 'Máy không tồn tại trong môi trường.')
    if len(active_sessions(service, owner, eid)) >= MAX_ACTIVE_PER_ENVIRONMENT:
        raise HubError('TERMINAL_LIMIT', 'Đã có 2 phiên terminal đang mở cho môi trường này; đóng một phiên trước.', 409)
    ssm = _client(service, env, clients)
    # No DocumentName: Session Manager uses the account's default shell document
    # (SSM-SessionManagerRunShell), which IAM checks via SessionDocumentAccessCheck.
    response = ssm.start_session(Target=instances[node], Reason=('CloudHub ' + eid)[:256])
    now = int(service.clock())
    row = _record(service, env, owner, response['SessionId'], instances[node], now)
    service.store.commit([row], {row['pk']: None})
    return {'session_id': response['SessionId'], 'stream_url': response['StreamUrl'], 'token': response['TokenValue'],
            'instance_index': node, 'region': service.region_for(env), 'started_at': now,
            'note': 'Token dùng một lần, chỉ cho trình duyệt của bạn; CloudHub không lưu token.'}


def end(service, owner, eid, session_id, clients=None):
    if not isinstance(session_id, str) or not SESSION_ID.fullmatch(session_id):
        raise HubError('INVALID_INPUT', 'Mã phiên không hợp lệ.')
    row = service.owned('T', session_id, owner)
    if row['environment_id'] != eid:
        raise HubError('NOT_FOUND', 'Không tìm thấy phiên.', 404)
    if row['status'] == 'ACTIVE':
        env = service.owned('E', eid, owner)
        try:
            _client(service, env, clients).terminate_session(SessionId=session_id)
        except Exception as exc:  # already closed by the agent or idle timeout
            if 'DoesNotExist' not in type(exc).__name__ and 'InvalidParameter' not in str(exc):
                raise
        row.update(status='ENDED', ended_at=int(service.clock()))
        service.store.commit([row], {row['pk']: row.get('version')})
    return {'session_id': session_id, 'status': row['status'], 'ended_at': row['ended_at']}
