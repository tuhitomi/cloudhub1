"""Record what is actually deployed, so the repository can be compared with production.

Writes (read-only AWS calls; needs credentials that can read CloudFormation,
Lambda and the frontend bucket):

* infra/deployed/<region>/<stack>.json  the original template of every
  ``cloudhub*`` stack. NoEcho parameter values are never part of a template.
* infra/deployed/manifest.json          stack status and update time, template
  SHA-256, Lambda handler/CodeSha256/last update, and the SHA-256 of every
  frontend object, plus which git ref each frontend file and Lambda module
  matches (``--compare-ref``).

Usage: python scripts/snapshot_deployed.py --bucket <frontend bucket> --compare-ref origin/main
"""
import argparse, base64, hashlib, io, json, subprocess, zipfile
from pathlib import Path
from urllib.request import urlopen
import boto3

ROOT = Path(__file__).resolve().parents[1]
REGIONS = ['ap-southeast-1', 'us-east-1', 'ap-northeast-1']
LIVE = ('CREATE_COMPLETE', 'UPDATE_COMPLETE', 'IMPORT_COMPLETE', 'UPDATE_ROLLBACK_COMPLETE')
GENERATED_FRONTEND = {'config.js', 'maintenance.json', 'rum-config.json'}  # written at deploy time from stack outputs


def sha(data): return hashlib.sha256(data).hexdigest()
def norm(data): return data.replace(b'\r\n', b'\n')


def git_blob(ref, path):
    p = subprocess.run(['git', 'show', f'{ref}:{path}'], capture_output=True, cwd=ROOT)
    return None if p.returncode else norm(p.stdout)


def compare(data, path, refs):
    out = {}
    for ref in refs:
        blob = git_blob(ref, path)
        out[ref] = 'missing' if blob is None else ('same' if blob == norm(data) else 'differs')
    return out


def stacks(session):
    rows = []
    for region in REGIONS:
        cfn = session.client('cloudformation', region_name=region)
        for page in cfn.get_paginator('list_stacks').paginate(StackStatusFilter=list(LIVE)):
            for s in page['StackSummaries']:
                if not s['StackName'].startswith('cloudhub'):
                    continue
                body = cfn.get_template(StackName=s['StackName'], TemplateStage='Original')['TemplateBody']
                template = json.loads(body) if isinstance(body, str) else body
                text = json.dumps(template, indent=1, ensure_ascii=False) + '\n'
                path = ROOT / 'infra/deployed' / region / f"{s['StackName']}.json"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding='utf-8')
                rows.append({'region': region, 'stack': s['StackName'], 'status': s['StackStatus'],
                             'updated': str(s.get('LastUpdatedTime') or s['CreationTime']),
                             'resources': len(template.get('Resources', {})), 'template_sha256': sha(text.encode()),
                             'file': path.relative_to(ROOT).as_posix()})
    return rows


def lambdas(session, refs, prefix):
    lam = session.client('lambda', region_name=REGIONS[0])
    rows = []
    for page in lam.get_paginator('list_functions').paginate():
        for f in page['Functions']:
            if not f['FunctionName'].startswith(prefix):
                continue
            code = lam.get_function(FunctionName=f['FunctionName'])['Code']['Location']
            archive = zipfile.ZipFile(io.BytesIO(urlopen(code, timeout=60).read()))
            modules = {n: compare(archive.read(n), 'backend/' + n, refs) for n in archive.namelist() if n.startswith('cloudhub/') and n.endswith('.py')}
            rows.append({'function': f['FunctionName'], 'handler': f['Handler'], 'runtime': f['Runtime'],
                         'last_modified': f['LastModified'], 'code_sha256': base64.b64decode(f['CodeSha256']).hex(),
                         'modules': len(modules),
                         'modules_differing': {ref: sorted(n for n, r in modules.items() if r[ref] != 'same') for ref in refs}})
    return rows


def frontend(session, bucket, refs):
    s3 = session.client('s3', region_name=REGIONS[0])
    rows = []
    for page in s3.get_paginator('list_objects_v2').paginate(Bucket=bucket):
        for obj in page.get('Contents', []):
            key = obj['Key']
            data = s3.get_object(Bucket=bucket, Key=key)['Body'].read()
            row = {'key': key, 'sha256': sha(norm(data)), 'last_modified': str(obj['LastModified'])}
            row['repo'] = 'generated at deploy time' if key in GENERATED_FRONTEND else compare(data, 'frontend/' + key, refs)
            rows.append(row)
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bucket', required=True)
    p.add_argument('--function-prefix', default='cloudhub-pages-live-')
    p.add_argument('--compare-ref', action='append', default=[])
    p.add_argument('--profile')
    args = p.parse_args()
    refs = args.compare_ref or ['HEAD']
    session = boto3.Session(profile_name=args.profile)
    manifest = {'account': session.client('sts').get_caller_identity()['Account'], 'compared_with': refs,
                'stacks': stacks(session), 'lambda': lambdas(session, refs, args.function_prefix),
                'frontend': frontend(session, args.bucket, refs)}
    out = ROOT / 'infra/deployed/manifest.json'
    out.write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')
    differing = [r['key'] for r in manifest['frontend'] if isinstance(r['repo'], dict) and 'same' not in r['repo'].values()]
    print(json.dumps({'stacks': len(manifest['stacks']), 'lambda': len(manifest['lambda']),
                      'frontend_objects': len(manifest['frontend']), 'frontend_matching_no_ref': differing}))


if __name__ == '__main__':
    main()
