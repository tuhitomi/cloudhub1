"""Stepped load test against CloudHub's public, read-only endpoints.

Shows how the serverless platform scales: each stage runs N virtual users
(keep-alive HTTPS, think time between requests) for a fixed time, then the
next stage raises N. Results per stage and endpoint: throughput, status codes,
p50/p95/p99. Pair the time window with the SLO dashboard ("Lambda concurrency
vs account quota") to see concurrency follow the load.

Safety: GET only on public endpoints, at most 100 users, an identifying
User-Agent, and the ramp stops early if a stage's 5xx rate exceeds 10 %.
``/public/catalog`` is reported separately: its route is throttled at 5 rps
by design, so 429s there measure the throttle, not Lambda scaling.

Usage: python scripts/load_ramp.py --stages 10,25,50,100 --seconds 90 --out ramp.json
"""
import argparse, http.client, json, math, random, ssl, threading, time
from collections import defaultdict

TARGETS = [('api.cloudhub1.me', '/ui-context', 0.5), ('cloudhub1.me', '/', 0.4), ('api.cloudhub1.me', '/public/catalog', 0.1)]
MAX_USERS = 100
CTX = ssl.create_default_context()


def pick():
    r = random.random()
    for host, path, weight in TARGETS:
        if r < weight:
            return host, path
        r -= weight
    return TARGETS[0][:2]


def pct(values, q):
    values = sorted(values)
    return round(values[min(len(values) - 1, max(0, math.ceil(len(values) * q) - 1))]) if values else None


def stage(users, seconds, think):
    results, lock, stop = [], threading.Lock(), time.time() + seconds

    def user():
        conns = {}
        while time.time() < stop:
            host, path = pick(); start = time.perf_counter(); status = 0
            try:
                conn = conns.get(host) or http.client.HTTPSConnection(host, timeout=10, context=CTX); conns[host] = conn
                conn.request('GET', path, headers={'Accept-Encoding': 'gzip, br', 'User-Agent': 'CloudHub-LoadRamp/1 (owner test)'})
                response = conn.getresponse(); response.read(); status = response.status
            except Exception:
                conns.pop(host, None)
            with lock:
                results.append((host + path, status, (time.perf_counter() - start) * 1000))
            time.sleep(think)

    threads = [threading.Thread(target=user) for _ in range(users)]
    began = time.time()
    for t in threads:
        t.start(); time.sleep(min(0.05, 2 / users))
    for t in threads:
        t.join()
    elapsed = time.time() - began
    by = defaultdict(list)
    for name, status, ms in results:
        by[name].append((status, ms))
    summary = {'users': users, 'started_at': int(began), 'seconds': round(elapsed, 1), 'requests': len(results),
               'throughput_rps': round(len(results) / elapsed, 1), 'endpoints': {}}
    for name, rows in sorted(by.items()):
        ok = [ms for s, ms in rows if s == 200]
        summary['endpoints'][name] = {'requests': len(rows), 'ok': len(ok),
            'codes': {str(c): sum(1 for s, _ in rows if s == c) for c in sorted({s for s, _ in rows})},
            'p50_ms': pct(ok, .5), 'p95_ms': pct(ok, .95), 'p99_ms': pct(ok, .99)}
    scaled = [r for r in results if '/public/catalog' not in r[0]]
    summary['error_5xx_rate'] = round(sum(1 for _, s, _ in scaled if s >= 500 or s == 0) / max(1, len(scaled)), 4)
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stages', default='10,25,50,100'); p.add_argument('--seconds', type=int, default=90)
    p.add_argument('--think', type=float, default=0.5); p.add_argument('--out', required=True)
    args = p.parse_args()
    stages = [int(x) for x in args.stages.split(',')]
    if max(stages) > MAX_USERS or args.seconds > 300:
        raise SystemExit('Refusing: at most 100 users and 300 s per stage')
    report = {'tool': 'load_ramp', 'targets': TARGETS, 'stages': []}
    for users in stages:
        result = stage(users, args.seconds, args.think)
        report['stages'].append(result)
        print(json.dumps({k: result[k] for k in ('users', 'throughput_rps', 'error_5xx_rate')}), flush=True)
        if result['error_5xx_rate'] > 0.10:
            report['stopped_early'] = f'5xx rate {result["error_5xx_rate"]:.1%} at {users} users'
            break
        time.sleep(20)
    with open(args.out, 'w', encoding='utf-8') as handle:
        json.dump(report, handle, indent=1)


if __name__ == '__main__':
    main()
