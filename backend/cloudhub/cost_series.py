"""Daily actual cost (Cost Explorer) next to the estimate for one environment.

Actual values come only from the last reconciled ``cost_report`` (POST
/environments/{id}/cost). Missing days stay ``null``; they are never shown as 0.
The estimate line spreads the environment's hourly running estimate over the
UTC hours it existed each day. It ignores paused periods, so it is an upper
envelope for paused environments, and it excludes one-off provisioning and
backup allowances that the first-period quote already contains.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING

MAX_DAYS = 62


def _day(ts):
    return datetime.fromtimestamp(int(ts), timezone.utc).date()


def hourly_estimate(service, env):
    from .catalog import environment_configuration
    quote = service.estimator_for(env).estimate(env['template_id'], 1, renewal=True, backup=False,
                                                 configuration=environment_configuration(env), workload=env.get('planning_workload'))
    return quote['total_milliusd'] if quote['approved'] else None


def series(service, owner, eid):
    env = service.owned('E', eid, owner)
    now = int(service.clock())
    start = int(env.get('ready_at') or env['created_at'])
    stop = int(env.get('deleted_at') or env.get('retired_at') or now) if env['status'] in {'DELETED', 'RESIDUAL'} else now
    stop = max(start, min(stop, now))
    first, last = _day(start), _day(stop)
    if (last - first).days >= MAX_DAYS:
        first = last - timedelta(days=MAX_DAYS - 1)
    hourly = hourly_estimate(service, env)
    report = env.get('cost_report') or {}
    actual = {d['date']: d for d in report.get('days', [])}
    rows, est_total, act_total = [], Decimal(0), 0
    day = first
    while day <= last:
        day_start = int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp())
        seconds = max(0, min(stop, day_start + 86400) - max(start, day_start))
        estimated = None if hourly is None else int((Decimal(hourly) * seconds / 3600).to_integral_value(rounding=ROUND_CEILING))
        found = actual.get(day.isoformat())
        value = int(found['milliusd']) if found else None
        if estimated is not None:
            est_total += estimated
        if value is not None:
            act_total += value
        rows.append({'date': day.isoformat(), 'running_hours': round(seconds / 3600, 2), 'estimated_milliusd': estimated,
                     'actual_milliusd': value, 'actual_is_estimated_by_aws': bool(found and found.get('estimated'))})
        day += timedelta(days=1)
    have_actual = [r for r in rows if r['actual_milliusd'] is not None]
    return {'environment_id': eid, 'currency': 'USD', 'hourly_estimate_milliusd': hourly,
            'report_status': report.get('status', 'NOT_REQUESTED'), 'report_checked_at': report.get('checked_at'),
            'days': rows, 'estimated_total_milliusd': int(est_total) if hourly is not None else None,
            'actual_total_milliusd': act_total if have_actual else None,
            'difference_milliusd': (act_total - int(sum(r['estimated_milliusd'] or 0 for r in have_actual))) if have_actual and hourly is not None else None,
            'assumptions': ['Ước tính = đơn giá theo giờ × số giờ môi trường tồn tại trong ngày UTC; không trừ thời gian tạm dừng.',
                            'Chi phí thực tế lấy từ lần đối soát Cost Explorer gần nhất, có độ trễ; ngày chưa có dữ liệu để trống, không tính là 0.',
                            'Không gồm phí dựng ban đầu, bản sao giữ lại và hạ tầng dùng chung.']}
