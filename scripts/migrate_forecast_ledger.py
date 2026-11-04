"""Preview first. Classify legacy amounts without reset, refund or budget increase."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from cloudhub.ledger import normalize
from cloudhub.quotes import fingerprint


def prepare(rows,now):
    result=[]
    for row in rows:
        if not row['pk'].startswith('Q#') or row.get('ledger_schema')==2:continue
        target=normalize(deepcopy(row),now)
        result.append({'pk':row['pk'],'expected_version':row.get('version'),
                       'source_fingerprint':fingerprint(row),'target':target})
    return {'schema':1,'mode':'PREVIEW_ONLY','created_at':now,'budget_changes':0,'refunds':0,
            'items':result,'warning':'All old commitments remain legacy_unallocated until separately reconciled. This is not AWS billing.'}


def apply_plan(store,plan):
    from cloudhub.errors import HubError
    for item in plan['items']:
        row=store.get(item['pk'])
        if row and row.get('ledger_schema')==2:continue
        if not row or fingerprint(row)!=item['source_fingerprint']:
            raise HubError('MIGRATION_CONFLICT','Ledger changed after preview; prepare and review again.',409)
        target=item['target']
        if fingerprint(target)!=fingerprint(normalize(deepcopy(row),plan['created_at'])):
            raise HubError('MIGRATION_INVALID','The preview changes fields outside the migration schema.',409)
        if int(target['reserved_milliusd'])!=int(row.get('reserved_milliusd',0)):
            raise HubError('MIGRATION_INVALID','Migration cannot change the commitment.',409)
        event={'pk':'M#forecast-v2-'+hashlib.sha256(row['pk'].encode()).hexdigest()[:24],
               'kind':'ledger_migration','source':deepcopy(row),'target_fingerprint':fingerprint(target),
               'created_at':plan['created_at'],'refunds':0}
        store.commit([target,event],{target['pk']:row.get('version'),event['pk']:None})


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot',type=Path,required=True,help='Read-only exported quota rows, JSON list')
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--apply',action='store_true');p.add_argument('--reviewed-sha256');p.add_argument('--table');p.add_argument('--region')
    args=p.parse_args()
    if not args.apply:
        from datetime import datetime,timezone
        plan=prepare(json.loads(args.snapshot.read_text(encoding='utf-8')),int(datetime.now(timezone.utc).timestamp()))
        args.out.write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print('Preview only; no AWS mutation. Review the plan before any apply.')
    else:
        data=args.out.read_bytes()
        if not args.table or not args.region or hashlib.sha256(data).hexdigest()!=args.reviewed_sha256:
            p.error('Exact reviewed plan SHA-256, table and Region are required for apply')
        import boto3
        from cloudhub.store import DynamoStore
        apply_plan(DynamoStore(args.table,boto3.client('dynamodb',region_name=args.region)),json.loads(data))
        print('Legacy amounts classified; no budgets or commitments changed.')

if __name__=='__main__':main()
