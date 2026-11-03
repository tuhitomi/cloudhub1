"""Reversible presentation filtering; never used for quota, workflow or ledger scans."""
from .errors import HubError

def include_tests(query):
    value=query.get('include_test','false')
    if value not in {'true','false'}:
        raise HubError('INVALID_INPUT','include_test must be true or false.')
    return value=='true'

def marked(row):
    value=row.get('test_data') or {}
    return isinstance(value,dict) and value.get('schema')==1 and value.get('classification')=='TEST' and value.get('hidden_by_default') is True

def hidden_environment(row):
    report=row.get('cleanup_report') or {}
    if not isinstance(report,dict):return False
    return (marked(row) and row.get('status')=='DELETED' and row.get('quota_released') is True
        and not any(row.get(k) for k in ['lock','cost_lock','needs_admin'])
        and bool(report.get('checked_at')) and not report.get('residual') and not report.get('unknown'))

def environments(rows,query,public):
    include=include_tests(query);hidden=[r for r in rows if hidden_environment(r)]
    # Old retirement reports can describe retained copies even after a later
    # backup deletion. Do not invent a current clean audit or conceal that scope.
    retained=sum(bool((r.get('cleanup_report') or {}).get('retained') or (r.get('cleanup_report') or {}).get('billable') or (r.get('cleanup_report') or {}).get('pending_deletion')) for r in hidden)
    return {'items':[public(r) for r in rows if include or not hidden_environment(r)],
        'hidden_test_count':0 if include else len(hidden),
        'retained_test_report_count':retained,'test_data_included':include}

def hidden_account(user,profile):
    # An enabled account is always shown, including a wrongly marked human.
    return marked(profile or {}) and user.get('enabled') is False and (profile or {}).get('enabled') is False
