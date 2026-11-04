"""Preview/pin legacy implicit wallet caps. No refunds, counter resets or AWS I/O on import."""
import hashlib
from copy import deepcopy

def plan(rows,legacy_cap_milliusd):
    if type(legacy_cap_milliusd) is not int or legacy_cap_milliusd<0:raise ValueError('Verified former runtime cap required')
    items=[]
    for row in rows:
        pk=row.get('pk','')
        if not pk.startswith('Q#') or len(pk)<=2 or pk=='Q#GLOBAL' or 'budget_milliusd' in row:continue
        items.append({'pk':pk,'previous_version':row.get('version'),'pin_milliusd':legacy_cap_milliusd,
                      'preserved_committed_milliusd':int(row.get('reserved_milliusd',0))+int(row.get('observed_unreserved_milliusd',0))})
    return {'schema':1,'legacy_cap_milliusd':legacy_cap_milliusd,'items':sorted(items,key=lambda v:v['pk']),
            'financial_effect':'Preserve the previous effective allocation and every forecast counter. No registration grant, refund, or platform-budget increase.'}

def pin(store,item,now):
    if (not isinstance(item.get('pk'),str) or not item['pk'].startswith('Q#') or len(item['pk'])<=2 or item['pk']=='Q#GLOBAL'
        or type(item.get('pin_milliusd')) is not int or item['pin_milliusd']<0):raise ValueError('Only an explicit legacy account cap may be pinned')
    from cloudhub.service import expected,retry
    def commit():
        row=store.get(item['pk'])
        if row is None:return 'MISSING_REVIEW_REQUIRED'
        if 'budget_milliusd' in row:return 'ALREADY_EXPLICIT'
        # Concurrent accounting may have changed counters. Preserve the fresh
        # row, then fence that exact version rather than overwriting a snapshot.
        changed=deepcopy(row);changed.update(budget_milliusd=item['pin_milliusd'],wallet_schema=1,wallet_cap_pinned_at=now)
        marker={'pk':'M#wallet-cap-'+hashlib.sha256(item['pk'].encode()).hexdigest()[:24],
                'kind':'wallet_migration','quota_pk':item['pk'],'legacy_cap_milliusd':item['pin_milliusd'],
                'created_at':now,'reason':'PIN_PREVIOUS_IMPLICIT_ALLOCATION','is_aws_actual':False}
        if store.get(marker['pk']) is not None:return 'INCONSISTENT_REVIEW_REQUIRED'
        store.commit([changed,marker],expected(changed,marker));return 'PINNED'
    return retry(commit)
