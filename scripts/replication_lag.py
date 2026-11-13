"""Measure DynamoDB global-table replication lag (the RPO of a regional failover).

Writes N probe items (pk ``DRPROBE#<run>#<i>``, outside every application key
prefix) in the primary Region, polls the replica with strongly consistent reads
until each item appears, then deletes the probes and checks that the deletes
replicate too. Requires boto3 and credentials allowed to write the table.

Usage: python scripts/replication_lag.py --table <name> --count 20 --out lag.json
"""
import argparse, json, math, time, uuid
import boto3

PRIMARY, REPLICA = 'ap-southeast-1', 'ap-northeast-1'


def pct(values, q):
    values = sorted(values)
    return round(values[min(len(values) - 1, max(0, math.ceil(len(values) * q) - 1))]) if values else None


def wait_for(table, key, present, timeout=30):
    start = time.perf_counter()
    while time.perf_counter() - start < timeout:
        item = table.get_item(Key=key, ConsistentRead=True).get('Item')
        if (item is not None) == present:
            return (time.perf_counter() - start) * 1000
        time.sleep(0.05)
    raise TimeoutError(f'{key} not {"present" if present else "deleted"} in replica after {timeout} s')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--table', required=True); p.add_argument('--count', type=int, default=20); p.add_argument('--out', required=True)
    args = p.parse_args()
    if args.count > 50:
        raise SystemExit('Refusing: at most 50 probes')
    primary = boto3.resource('dynamodb', region_name=PRIMARY).Table(args.table)
    replica = boto3.resource('dynamodb', region_name=REPLICA).Table(args.table)
    run, lags, delete_lags = uuid.uuid4().hex[:8], [], []
    keys = [{'pk': f'DRPROBE#{run}#{i}'} for i in range(args.count)]
    try:
        for key in keys:
            primary.put_item(Item={**key, 'kind': 'dr-probe', 'written_at': int(time.time())})
            # Includes one replica read round trip (~70 ms Tokyo from Vietnam), so it is an upper bound.
            lags.append(wait_for(replica, key, True))
    finally:
        for key in keys:
            primary.delete_item(Key=key)
    for key in keys[:5]:
        delete_lags.append(wait_for(replica, key, False))
    result = {'tool': 'replication_lag', 'table': args.table, 'from': PRIMARY, 'to': REPLICA, 'probes': args.count,
              'lag_ms': {'p50': pct(lags, .5), 'p95': pct(lags, .95), 'max': round(max(lags))},
              'delete_lag_ms_max': round(max(delete_lags)), 'samples_ms': [round(x) for x in lags]}
    with open(args.out, 'w', encoding='utf-8') as handle:
        json.dump(result, handle, indent=1)
    print(json.dumps({k: v for k, v in result.items() if k != 'samples_ms'}))


if __name__ == '__main__':
    main()
