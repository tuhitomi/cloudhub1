"""Owned notification history and a durable, opt-in email outbox.

Email is best effort. A publish with an unknown outcome is never blindly retried.
Reading a notification does not change environment policy or accept a quote.
"""
from copy import deepcopy
import re
from .errors import HubError
from .operating_policy import current_policy, revision

WARNING_SECONDS = 900
TYPES = {'EXPIRY_SOON', 'RENEWAL_SUCCEEDED', 'RENEWAL_BLOCKED', 'RENEWAL_SYNC_PENDING',
         'CONTINUOUS_BUDGET_WARNING', 'CONTINUOUS_COST_UNAVAILABLE','MAINTENANCE_NOTICE'}
PUBLIC = {'notification_id', 'environment_id', 'template_id', 'region', 'type', 'created_at',
          'deadline', 'lifecycle_revision', 'ending_policy', 'mode', 'automatic', 'minutes',
          'period_estimate_milliusd', 'cumulative_milliusd', 'budget_limit_milliusd',
          'code', 'read_at', 'operation_id', 'email_status', 'currency', 'threshold_milliusd',
          'announcement_id','title','message','impact','starts_at','ends_at','language','notice_kind','published_at','revision'}

def email_channel(row):
    return 'maintenance_email' if row['type']=='MAINTENANCE_NOTICE' else 'expiry_email' if row['type']=='EXPIRY_SOON' else 'renewal_email'


def settings_key(owner):
    return 'P#notifications-' + owner


def reminder_id(env):
    suffix = '-v' + str(revision(env)) if revision(env) else ''
    return env['environment_id'] + '-' + str(env['deadline']) + suffix


def due(env, now):
    return (env and current_policy(env)['mode'] != 'CONTINUOUS'
            and env.get('status') in {'READY', 'BACKING_UP'} and env.get('deadline') is not None
            and 0 < env['deadline'] - now <= WARNING_SECONDS)


def notice(service, env, kind, nid, **fields):
    from .service import record
    existing = service.store.get('N#' + nid)
    if existing:
        return None
    policy = current_policy(env)
    pref = service.store.get(settings_key(env['owner_id'])) or {}
    channel = 'expiry_email' if kind == 'EXPIRY_SOON' else 'renewal_email'
    enabled = pref.get('email_enabled') is True and pref.get(channel, True) is True
    row = record('notification', nid, env['owner_id'], notification_id=nid,
                  environment_id=env['environment_id'], template_id=env['template_id'],
                  region=service.region_for(env), type=kind, created_at=int(service.clock()),
                  deadline=env.get('deadline'), lifecycle_revision=revision(env),
                  ending_policy=policy['ending_policy'], mode=policy['mode'],
                  budget_limit_milliusd=policy.get('budget_limit_milliusd'),
                  cumulative_milliusd=env.get('estimated_committed_milliusd'), currency='USD',
                  read_at=None, email_status='PENDING' if enabled else 'NOT_REQUESTED', **fields)
    if kind == 'EXPIRY_SOON' and policy['mode'] == 'AUTO_RENEW':
        row['period_estimate_milliusd'] = env.get('cost_plan', {}).get('renewal_period', {}).get('total_milliusd')
    return row


def operation_notices(service, op, env, status):
    from .service import ident
    original = env.get('last_renewal') or {}
    repair = (op.get('repair_only') and original.get('operation_id')
              and original.get('lifecycle_revision') == revision(env) and op.get('target_revision') == revision(env))
    if (op.get('action') != 'renew' and not repair) or op.get('superseded'):
        return []
    oid = original['operation_id'] if repair else op['operation_id']
    if status == 'SUCCEEDED' and op.get('result', {}).get('schedule_synced') is True:
        kind = 'RENEWAL_SUCCEEDED'
    else:
        # Deadline and cost already committed: never call this a rejected renewal.
        kind = 'RENEWAL_SYNC_PENDING'
    row = notice(service, env, kind, ident('notice-', oid, kind), operation_id=oid,
                 automatic=bool(original.get('automatic', op.get('automatic', False))),
                 minutes=original.get('minutes', op.get('minutes')),
                 period_estimate_milliusd=original.get('period_estimate', {}).get('total_milliusd'))
    return [row] if row else []


class NotificationCenter:
    def __init__(self, service):
        self.s = service

    def current(self, item):
        if item.get('type')=='MAINTENANCE_NOTICE':
            from .announcements import Announcements
            return Announcements(self.s).current(item)
        if item.get('type') != 'EXPIRY_SOON':
            return True
        env = self.s.store.get('E#' + item['environment_id'])
        return bool(env and env['owner_id'] == item['owner_id'] and due(env, int(self.s.clock()))
                    and env.get('deadline') == item.get('deadline')
                    and revision(env) == item.get('lifecycle_revision', 0))

    def public(self, row):
        item = {key: deepcopy(value) for key, value in row.items() if key in PUBLIC}
        item['current'] = self.current(row)
        item['read_at'] = row.get('read_at')
        item['remaining_seconds'] = max(0, int(row.get('deadline') or 0) - int(self.s.clock()))
        return item

    def list(self, owner):
        rows = {row['notification_id']: row for row in self.s.store.list_owner(owner, 'notification')
                if row.get('type') in TYPES}
        from .announcements import Announcements
        for row in Announcements(self.s).virtual(owner):
            stored=rows.get(row['notification_id'])
            if stored:row.update({k:stored[k] for k in ['version','read_at','email_status'] if k in stored})
            rows[row['notification_id']]=row
        # Preserve the immediate 15-minute preview even between five-minute sweeps.
        # A GET does not write; marking this preview read materializes it safely.
        for env in self.s.store.list_owner(owner, 'environment'):
            if due(env, int(self.s.clock())):
                nid = reminder_id(env)
                if nid not in rows:
                    row = notice(self.s, env, 'EXPIRY_SOON', nid)
                    if row:
                        row['created_at'] = max(int(env.get('created_at', 0)), env['deadline'] - WARNING_SECONDS)
                        rows[nid] = row
        ordered = sorted(rows.values(), key=lambda r: (r.get('created_at', 0), r['notification_id']), reverse=True)
        active = [row for row in ordered if self.current(row)]
        return {'items': [self.public(row) for row in active[:100]],
                'history': [self.public(row) for row in ordered[:100]],
                'unread_count': sum(not row.get('read_at') for row in active),
                'total_count': len(ordered), 'truncated': len(ordered) > 100, 'warning_minutes': 15}

    def remind(self, eid):
        from .service import expected, retry
        def commit():
            env = self.s.store.get('E#' + eid)
            if not due(env, int(self.s.clock())):
                return None
            nid = reminder_id(env)
            row = notice(self.s, env, 'EXPIRY_SOON', nid)
            if not row:
                return None
            env.update(reminded_deadline=env['deadline'], reminded_revision=revision(env))
            self.s.store.commit([env, row], expected(env, row))
            return row
        return retry(commit)

    def read(self, owner, nid):
        from .service import expected, retry
        if not isinstance(nid, str) or not re.fullmatch(r'[a-z0-9-]{1,160}', nid):
            raise HubError('INVALID_INPUT', 'Invalid notification ID.')
        def commit():
            row = self.s.store.get('N#' + nid)
            if not row:
                from .announcements import Announcements
                row=next((r for r in Announcements(self.s).virtual(owner) if r['notification_id']==nid),None)
            if not row:
                env = next((env for env in self.s.store.list_owner(owner, 'environment')
                            if due(env, int(self.s.clock())) and reminder_id(env) == nid), None)
                if env:
                    self.remind(env['environment_id'])
                    row = self.s.store.get('N#' + nid)
            if not row or row.get('owner_id') != owner or row.get('type') not in TYPES:
                raise HubError('NOT_FOUND', 'Notification not found.', 404)
            if not row.get('read_at'):
                row['read_at'] = int(self.s.clock())
                self.s.store.commit([row], expected(row))
            return self.public(row)
        return retry(commit)

    def preferences(self, owner, email_available=False):
        row = self.s.store.get(settings_key(owner)) or {}
        return {key: row.get(key, default) for key, default in {
            'email_enabled': False, 'expiry_email': True, 'renewal_email': True,'maintenance_email':False,
            'email_status': 'DISABLED', 'masked_email': None, 'updated_at': None}.items()} | {
                'email_available': bool(email_available), 'delivery_verified': False}

    def preferences_update(self, owner, body, gateway=None, identity=None):
        from .service import expected, retry, record, ident
        if (not {'email_enabled','expiry_email','renewal_email'}<=set(body) or set(body)-{'email_enabled','expiry_email','renewal_email','maintenance_email'}
            or any(type(v) is not bool for v in body.values())):
            raise HubError('INVALID_INPUT', 'Only boolean notification preferences are accepted.')
        if body['email_enabled'] and (gateway is None or not identity or identity.get('owner_id') != owner
                                     or identity.get('email_verified') is not True):
            raise HubError('NOTIFICATION_EMAIL_UNAVAILABLE', 'Email delivery is not enabled or the address is unverified.', 503)
        token = ident('setup-', owner, str(self.s.clock()), gateway.token() if gateway else '')
        def commit():
            row = self.s.store.get(settings_key(owner)) or record('preference', 'notifications-' + owner, owner)
            now = int(self.s.clock())
            if row.get('setup_until', 0) > now:
                # Opt-out always wins, including while SNS setup is in flight.
                if body['email_enabled']:
                    raise HubError('NOTIFICATION_SETUP_BUSY', 'Email setup is in progress; check its status shortly.', 409)
            reuse = (body['email_enabled'] and row.get('email_enabled') and row.get('address') == identity['email']
                     and row.get('email_status') in {'CONFIRMED', 'PENDING_CONFIRMATION', 'SETUP_UNKNOWN'})
            allow_subscribe = now - row.get('subscription_attempt_at', -300) >= 300
            if body.get('maintenance_email') is True and (not row.get('maintenance_email') or row.get('address')!=(identity or {}).get('email')):
                row['maintenance_email_enabled_since']=now
            if body['email_enabled'] and (not row.get('email_enabled') or row.get('address') != identity['email']):
                row['email_enabled_since'] = now
            row.update(body, updated_at=now, setup_token=token)
            if body['email_enabled']:
                row.update(address=identity['email'], username=identity.get('username', owner),
                           email_status=row.get('email_status') if reuse else 'SETTING_UP', setup_until=0 if reuse else now + 60)
                if not reuse and allow_subscribe:row['subscription_attempt_at']=now
            else:
                row.update(email_status='DISABLED', setup_until=0)
            self.s.store.commit([row], expected(row))
            return row, reuse, allow_subscribe
        row, reuse, allow_subscribe = retry(commit)
        if not body['email_enabled']:
            return self.preferences(owner, gateway is not None)
        if reuse:
            return self.preferences(owner, True)
        try:
            result = gateway.configure(owner, identity['email'], allow_subscribe=allow_subscribe)
        except Exception:
            result = {'email_status': 'SETUP_UNKNOWN'}
        def complete():
            fresh = self.s.store.get(settings_key(owner))
            if fresh.get('setup_token') != token or not fresh.get('email_enabled'):
                return
            fresh.update(result, setup_until=0)
            self.s.store.commit([fresh], expected(fresh))
        retry(complete)
        return self.preferences(owner, True)

    def preferences_check(self, owner, gateway=None, identity=None):
        from .service import expected, retry
        row = self.s.store.get(settings_key(owner))
        if not row or not row.get('email_enabled') or gateway is None:
            return self.preferences(owner, gateway is not None)
        if not identity or identity.get('owner_id') != owner or identity.get('email_verified') is not True or identity.get('email') != row.get('address'):
            raise HubError('NOTIFICATION_ADDRESS_CHANGED', 'Save email preferences again after verifying the current address.', 409)
        result = gateway.check(owner, identity['email'])  # Read-only; never resend confirmation.
        token = row.get('setup_token')
        def commit():
            fresh = self.s.store.get(settings_key(owner))
            if fresh and fresh.get('email_enabled') and fresh.get('setup_token') == token:
                fresh.update(result)
                self.s.store.commit([fresh], expected(fresh))
        retry(commit)
        return self.preferences(owner, True)

    def drain(self, gateway, identity_lookup, limit=10):
        """Called by the existing sweep, not a long-running API request."""
        from .service import expected, retry
        from .announcements import Announcements
        results = []
        pending = sorted((r for r in self.s.store.scan_kind('notification')
                          if r.get('email_status') in {'PENDING', 'SENDING'} and r.get('email_attempt_after', 0) <= self.s.clock()),
                         key=lambda r: (r.get('email_attempted_at', 0), r.get('created_at', 0)))
        for candidate in pending[:limit]:
            owner = candidate['owner_id']
            def claim():
                row = self.s.store.get(candidate['pk'])
                if row.get('email_status') == 'SENDING':
                    if row.get('email_lease_until', 0) <= self.s.clock():
                        row['email_status'] = 'UNKNOWN'
                        self.s.store.commit([row], expected(row))
                    return None
                if row.get('email_status') != 'PENDING':
                    return None
                pref = self.s.store.get(settings_key(owner)) or {}
                channel = email_channel(row)
                if (not pref.get('email_enabled') or not pref.get(channel, channel!='maintenance_email')
                        or row.get('created_at', 0) < max(pref.get('email_enabled_since', 0),pref.get('maintenance_email_enabled_since',0) if channel=='maintenance_email' else 0)):
                    row['email_status'] = 'SKIPPED_OPT_OUT'
                elif not (self.current(row) if channel!='maintenance_email' else Announcements(self.s).email_current(row)) or self.s.clock() - row['created_at'] > 86400:
                    row['email_status'] = 'SKIPPED_STALE'
                else:
                    row.update(email_status='SENDING', email_token=gateway.token(), email_lease_until=int(self.s.clock()) + 60,
                               email_attempted_at=int(self.s.clock()))
                self.s.store.commit([row], expected(row))
                return row if row['email_status'] == 'SENDING' else None
            row = retry(claim)
            if not row:
                continue
            def still_current():
                pref = self.s.store.get(settings_key(owner)) or {}
                channel = email_channel(row)
                from .announcements import Announcements
                current=Announcements(self.s).email_current(row) if channel=='maintenance_email' else self.current(row)
                return bool(pref.get('email_enabled') and pref.get(channel, channel!='maintenance_email') and current
                            and pref.get('address') == address)
            try:
                pref = self.s.store.get(settings_key(owner)) or {}
                address = pref.get('address')
                identity = identity_lookup(owner, pref.get('username'))
                if identity.get('owner_id') != owner or identity.get('email_verified') is not True or identity.get('email') != address:
                    outcome = {'email_status': 'SKIPPED_ADDRESS_CHANGED'}
                else:
                    profile = self.s.store.get('U#' + owner) or {}
                    outcome = gateway.send(owner, address, row, profile.get('language_preference', 'en'), still_current)
            except Exception:
                # We cannot distinguish a lost publish response from a rejected one.
                outcome = {'email_status': 'UNKNOWN'}
            def finish():
                fresh = self.s.store.get(row['pk'])
                if fresh.get('email_token') != row.get('email_token') or fresh.get('email_status') != 'SENDING':
                    return
                fresh.update(outcome, email_checked_at=int(self.s.clock()))
                if outcome['email_status'] == 'PENDING':fresh['email_attempt_after']=int(self.s.clock())+300
                self.s.store.commit([fresh], expected(fresh))
            retry(finish)
            results.append({'notification_id': row['notification_id'], 'status': outcome['email_status']})
        return results
