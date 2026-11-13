"""Observe CloudHub from a visitor's side during a chaos experiment.

Once a second it requests the home page, the edge-cached public catalog and the
API's /ui-context, and records status, cache result and whether the catalog
came from the Tokyo recovery snapshot (x-amz-meta-snapshot-at). GET only, about
three requests per second.

Usage: python scripts/chaos_probe.py --seconds 420 --out probe.json
"""
import argparse, http.client, json, ssl, time

PROBES = [('home', 'cloudhub1.me', '/'), ('catalog', 'cloudhub1.me', '/public/catalog'), ('api', 'api.cloudhub1.me', '/ui-context')]
CTX = ssl.create_default_context()


def get(host, path):
    start = time.perf_counter()
    try:
        conn = http.client.HTTPSConnection(host, timeout=5, context=CTX)
        conn.request('GET', path, headers={'Accept-Encoding': 'gzip, br', 'User-Agent': 'CloudHub-ChaosProbe/1 (owner test)'})
        r = conn.getresponse(); r.read(); conn.close()
        return {'status': r.status, 'ms': round((time.perf_counter() - start) * 1000), 'cache': r.getheader('x-cache'),
                'snapshot': r.getheader('x-amz-meta-snapshot-at'), 'age': r.getheader('age')}
    except Exception as error:
        return {'status': 0, 'ms': round((time.perf_counter() - start) * 1000), 'error': type(error).__name__}


def summarize(samples):
    """Collapse consecutive identical outcomes into segments for the timeline."""
    out = {}
    for name, _, _ in PROBES:
        segments = []
        for s in samples:
            r = s[name]; key = (r['status'], 'tokyo' if r.get('snapshot') else 'primary')
            if segments and segments[-1]['key'] == list(key):
                segments[-1]['to'] = s['t']; segments[-1]['count'] += 1
            else:
                segments.append({'key': list(key), 'from': s['t'], 'to': s['t'], 'count': 1})
        out[name] = segments
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--seconds', type=int, default=420); p.add_argument('--out', required=True)
    args = p.parse_args()
    if args.seconds > 1200:
        raise SystemExit('Refusing: at most 1200 s')
    began, samples = time.time(), []
    while time.time() - began < args.seconds:
        tick = time.time()
        sample = {'t': round(tick - began, 1), 'at': time.strftime('%H:%M:%S', time.localtime(tick))}
        for name, host, path in PROBES:
            sample[name] = get(host, path)
        samples.append(sample)
        print(json.dumps({k: (v['status'] if isinstance(v, dict) else v) for k, v in sample.items()}
                         | {'catalog_from': 'tokyo' if sample['catalog'].get('snapshot') else 'primary'}), flush=True)
        time.sleep(max(0, 1 - (time.time() - tick)))
    with open(args.out, 'w', encoding='utf-8') as handle:
        json.dump({'tool': 'chaos_probe', 'started_at': int(began), 'samples': samples, 'timeline': summarize(samples)}, handle, indent=1)


if __name__ == '__main__':
    main()
