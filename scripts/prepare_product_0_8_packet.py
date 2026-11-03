"""Build deterministic, private release artifacts; never uploads or mutates AWS."""
import argparse,hashlib,io,json,sys,zipfile
from pathlib import Path
from datetime import datetime,timezone
from public_assets import ASSETS
from prepare_product_release import source_digest
ROOT=Path(__file__).resolve().parents[1]

def digest(data):return hashlib.sha256(data).hexdigest()

def archive(files):
    buf=io.BytesIO()
    with zipfile.ZipFile(buf,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for name,data in sorted(files.items()):
            entry=zipfile.ZipInfo(name,(2000,1,1,0,0,0));entry.compress_type=zipfile.ZIP_DEFLATED;entry.external_attr=0o644<<16
            z.writestr(entry,data)
    return buf.getvalue()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--public-config',type=Path,required=True);p.add_argument('--deps',type=Path,required=True);p.add_argument('--out-dir',type=Path,required=True)
    p.add_argument('--deployment-target',type=Path,required=True,help='Reviewed account_id, primary_region and stack_name; no production default')
    a=p.parse_args()
    out=a.out_dir.resolve()
    if out.is_relative_to(ROOT):p.error('Binary release artifacts stay outside the source repository')
    manifest=json.loads(a.manifest.read_text(encoding='utf-8'))
    if manifest.get('ready_for_native_review') is not True:raise ValueError('Complete repository sources and native-scope local checks are required before packaging')
    if manifest['tests']['passed'] is not True:raise ValueError('All corresponding local checks must pass')
    target=json.loads(a.deployment_target.read_text(encoding='utf-8'))
    if (not str(target.get('account_id','')).isdigit() or len(str(target['account_id']))!=12
        or target.get('primary_region') not in {'ap-southeast-1','ap-northeast-1','us-east-1'}
        or not str(target.get('stack_name','')).startswith('cloudhub-')):raise ValueError('A reviewed deployment target is required')
    from build_pages_live import build
    for name,expected in manifest['files'].items():
        checksum=source_digest((ROOT/name).read_bytes()) if manifest.get('fingerprint_format')=='UTF8_LF_SHA256' else digest((ROOT/name).read_bytes())
        if checksum!=expected:raise ValueError('Manifest source drift: '+name)
    out.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(a.deps.resolve()));import boto3,botocore
    if (boto3.__version__,botocore.__version__)!=('1.43.110','1.43.110'):raise ValueError('Pinned SDK dependencies required')
    files={p.relative_to(ROOT/'backend').as_posix():p.read_bytes() for p in (ROOT/'backend').rglob('*.py') if '__pycache__' not in p.parts}
    for name in ['boto3','botocore','s3transfer','jmespath','dateutil','urllib3']:
        folder=a.deps/name
        if not folder.is_dir():raise ValueError('Missing dependency '+name)
        files.update({p.relative_to(a.deps).as_posix():p.read_bytes() for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'})
    files['six.py']=(a.deps/'six.py').read_bytes()
    for folder in a.deps.glob('*.dist-info'):
        if not folder.name.startswith(('boto3-','botocore-','s3transfer-','jmespath-','python_dateutil-','urllib3-','six-')):continue
        files.update({p.relative_to(a.deps).as_posix():p.read_bytes() for p in folder.rglob('*') if p.is_file()})
    code=archive(files);(out/'backend.zip').write_bytes(code)
    config=json.loads(a.public_config.read_text(encoding='utf-8'));build(out/'frontend',config)
    public={p.relative_to(out/'frontend').as_posix():p.read_bytes() for p in (out/'frontend').rglob('*') if p.is_file()}
    front=archive(public);(out/'frontend.zip').write_bytes(front)
    infra=(ROOT/'infra/control-plane.json').read_bytes();(out/'control-plane.generated.json').write_bytes(infra)
    # This is the generic repository IaC. Do not replace the deployed, transformed
    # template (which references retained data) with this file wholesale.
    packet={'recorded_at':datetime.now(timezone.utc).isoformat(),'status':'PREPARED_NOT_DEPLOYED',
        'base_commit':manifest['base_commit'],'source_snapshot_sha256':manifest['source_snapshot_sha256'],
        'backend':{'sha256':digest(code),'bytes':len(code),'files':len(files),'boto3':boto3.__version__,'botocore':botocore.__version__},
        'frontend':{'sha256':digest(front),'bytes':len(front),'assets':{k:digest(v) for k,v in public.items()}},
        'generated_iac_sha256':digest(infra),'tests_recorded_at':manifest['tests']['recorded_at'],
        'aws_deployed':False,'new_flags':{'CONTINUOUS_ENABLED':False,'DIRECT_UPLOAD_ENABLED':False},
        'target':{'account':str(target['account_id']),'control_region':target['primary_region'],'stack':target['stack_name'],
                  'functions':['ApiFunction','WorkerFunction','SweepFunction','ExpiryFunction']},
        'do_not_execute_generated_template_wholesale':True,
        'blockers':['Fresh authenticated inventory/credits/ledger and full retained-resource reconciliation',
                    'Native template adaptation, scoped IAM review/change set without replacements',
                    'Current complete price approval and bounded test forecast',
                    'Migration preview/hash review and AWS acceptance; no feature gate is opened by this packet'],
        'rollback':'Keep schema-2 compatible workers until new records/operations have drained. Never reset ledger or delete user resources for a code rollback.'}
    (out/'packet.json').write_text(json.dumps(packet,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({k:packet[k] for k in ['status','source_snapshot_sha256','backend','generated_iac_sha256','aws_deployed']}))

if __name__=='__main__':main()
