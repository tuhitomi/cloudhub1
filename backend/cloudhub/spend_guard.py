"""AWS spend guard.

AWS Budgets publishes to an SNS topic when the account's *actual* monthly cost
crosses a threshold. ``sns_handler`` turns that notification into one durable
DynamoDB row. While the row is frozen, every admission that starts or extends
compute (create, restore, renew, resume) is refused with SPEND_GUARD_ACTIVE.

Actions that reduce or protect spend stay available: end/destroy, backup,
export, delete of recovery points and the retirement retries that keep a
billable source from being stranded. An administrator clears the guard
explicitly; it never clears itself, because Budgets does not send an
"under threshold" event and actual cost data arrives with a delay.

The internal forecast budget (wallets, platform budget) is unrelated: it limits
*estimated* commitments, while this guard reacts to *billed* AWS cost.
"""
import json
import os
import re

from .errors import HubError

KEY = 'G#SPEND_GUARD'
HISTORY_LIMIT = 20
MESSAGE = ('Chi phí AWS thực tế đã chạm ngưỡng ngân sách; tạm dừng tạo, khôi phục và gia hạn môi trường. '
           'Kết thúc, sao lưu và xuất dữ liệu vẫn hoạt động.')


def current(service):
    return service.store.get(KEY)


def active(service):
    row = current(service)
    return row if row and row.get('frozen') else None


def details(row):
    return {'budget_scope': 'AWS_SPEND_GUARD', 'since': row.get('changed_at'), 'source': row.get('source'),
            'threshold_percent': row.get('threshold_percent'), 'budget_name': row.get('budget_name')}


def assert_open(service):
    """Raise when the guard is frozen. Call only on spend-increasing admissions."""
    row = active(service)
    if row:
        raise HubError('SPEND_GUARD_ACTIVE', MESSAGE, 409, details(row))


def view(service):
    row = current(service) or {}
    return {'frozen': bool(row.get('frozen')), 'source': row.get('source'), 'changed_at': row.get('changed_at'),
            'changed_by': row.get('changed_by'), 'reason': row.get('reason'), 'budget_name': row.get('budget_name'),
            'threshold_percent': row.get('threshold_percent'), 'actual_usd': row.get('actual_usd'),
            'limit_usd': row.get('limit_usd'), 'history': list(row.get('history', []))}


# AWS Budgets SNS messages are plain text, for example:
#   "You requested that we alert you when the ACTUAL Cost associated with your
#    cloudhub-monthly budget is greater than 100% of $50.00 for the current
#    month. The ACTUAL Cost associated with this budget is $51.20."
NOTICE = re.compile(r'when the (?P<kind>ACTUAL|FORECASTED) Cost associated with your (?P<name>[A-Za-z0-9_.:+=@-]+) budget '
                    r'is greater than (?P<pct>\d+(?:\.\d+)?)% of \$(?P<limit>[\d,]+(?:\.\d+)?)', re.I)
CURRENT = re.compile(r'The (?:ACTUAL|FORECASTED) Cost associated with this budget is \$(?P<value>[\d,]+(?:\.\d+)?)', re.I)


def parse(message):
    """Return the notification fields, or None for any other SNS message."""
    text = message if isinstance(message, str) else json.dumps(message)
    match = NOTICE.search(text)
    if not match:
        return None
    value = CURRENT.search(text)
    number = lambda raw: float(raw.replace(',', ''))
    return {'kind': match['kind'].upper(), 'budget_name': match['name'], 'threshold_percent': number(match['pct']),
            'limit_usd': number(match['limit']), 'actual_usd': number(value['value']) if value else None}


def _commit(service, update):
    from .service import retry, expected

    def transaction():
        row = current(service) or {'pk': KEY, 'kind': 'spend_guard', 'frozen': False, 'history': []}
        changed = update(row)
        if changed is False:
            return row
        row['history'] = ([changed] + list(row.get('history', [])))[:HISTORY_LIMIT]
        service.store.commit([row], expected(row))
        return current(service)
    return retry(transaction)


def freeze_from_budget(service, notice, now, budget_name=None, threshold=100.0):
    """Freeze on an ACTUAL notification for our budget at or above the threshold."""
    if notice['kind'] != 'ACTUAL' or notice['threshold_percent'] < threshold:
        return None
    if budget_name and notice['budget_name'] != budget_name:
        return None

    def update(row):
        event = {'at': now, 'action': 'FROZEN' if not row.get('frozen') else 'NOTIFIED', 'by': 'aws-budgets',
                 'threshold_percent': notice['threshold_percent'], 'actual_usd': notice['actual_usd']}
        if not row.get('frozen'):
            row.update(frozen=True, changed_at=now, changed_by='aws-budgets', source='AWS_BUDGETS', reason=None)
        row.update(budget_name=notice['budget_name'], threshold_percent=notice['threshold_percent'],
                   limit_usd=notice['limit_usd'], actual_usd=notice['actual_usd'], last_notification_at=now)
        return event
    return _commit(service, update)


def set_state(service, actor, body, now):
    """Administrator freeze or release. A reason is mandatory and audited."""
    if set(body) - {'frozen', 'reason'} or type(body.get('frozen')) is not bool:
        raise HubError('INVALID_INPUT', 'Gửi {"frozen": true|false, "reason": "..."}.')
    reason = body.get('reason')
    if not isinstance(reason, str) or not 10 <= len(reason.strip()) <= 500:
        raise HubError('INVALID_INPUT', 'Cần lý do từ 10 đến 500 ký tự.')

    def update(row):
        if bool(row.get('frozen')) == body['frozen']:
            return False
        row.update(frozen=body['frozen'], changed_at=now, changed_by=actor, source='ADMIN', reason=reason.strip())
        return {'at': now, 'action': 'FROZEN' if body['frozen'] else 'RELEASED', 'by': actor, 'reason': reason.strip()}
    _commit(service, update)
    return view(service)


def sns_handler(event, context=None, service=None, publish=None):
    """Lambda target of the Budgets SNS topic. Needs only the metadata table."""
    import time
    if service is None:
        from types import SimpleNamespace
        from .store import DynamoStore
        service = SimpleNamespace(store=DynamoStore(os.environ['TABLE_NAME']))
    if publish is None and os.getenv('ALERT_TOPIC_ARN'):
        import boto3
        client = boto3.client('sns')
        publish = lambda subject, text: client.publish(TopicArn=os.environ['ALERT_TOPIC_ARN'], Subject=subject, Message=text)
    threshold = float(os.getenv('SPEND_GUARD_THRESHOLD_PERCENT', '100'))
    budget_name = os.getenv('SPEND_GUARD_BUDGET_NAME') or None
    results = []
    for record in event.get('Records', []):
        notice = parse(record.get('Sns', {}).get('Message', ''))
        if notice is None:
            results.append('IGNORED_UNKNOWN_MESSAGE')
            continue
        before = active(service)
        row = freeze_from_budget(service, notice, int(time.time()), budget_name, threshold)
        results.append('FROZEN' if row and row.get('frozen') else 'BELOW_THRESHOLD_OR_FORECAST')
        if row and row.get('frozen') and not before and publish:
            publish('CloudHub spend guard frozen',
                    f"Actual AWS cost {notice['actual_usd']} USD reached {notice['threshold_percent']}% of "
                    f"{notice['limit_usd']} USD ({notice['budget_name']}). New creations, restores and renewals are "
                    "refused until an administrator releases POST /admin/spend-guard.")
        print(json.dumps({'event': 'CloudHubSpendGuard', 'result': results[-1], **notice}))
    return {'results': results}
