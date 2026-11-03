"""Prepare a text-source manifest; a local fixture PASS never approves deployment."""
import argparse,hashlib,json,subprocess
from datetime import datetime,timezone
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[1]
SUFFIXES={'.py','.js','.mjs','.json','.html','.css','.txt','.yml','.yaml'}

def safe_file(root,name):
    rel=PurePosixPath(name)
    if rel.is_absolute() or '..' in rel.parts or '.git' in rel.parts or ':' in name or '\\' in name:
        raise ValueError('Unsafe source path')
    path=root/name
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):raise ValueError('Source escapes repository')
    return path

def digest(raw):return hashlib.sha256(raw).hexdigest()
def source_digest(raw):return digest(raw.replace(b'\r\n',b'\n'))

def prepare(results,root=ROOT):
    root=Path(root).resolve()
    if not isinstance(results,dict) or results.get('scope') not in {'LOCAL_REPOSITORY','LOCAL_SUPPORT_FIXTURE'}:
        raise ValueError('Explicit local test scope is required')
    if results.get('passed') is not True:raise ValueError('Corresponding local checks must pass before preparing this manifest')
    if type(results.get('tests_run')) is not int or results['tests_run']<=0:raise ValueError('Actual test count is required')
    covered=results.get('covered_files')
    if not isinstance(covered,dict) or not covered:raise ValueError('Test source fingerprints are required')
    for name,expected in covered.items():
        path=safe_file(root,name)
        raw=path.read_bytes() if path.is_file() else None
        actual=(source_digest(raw) if results.get('fingerprint_format')=='UTF8_LF_SHA256' else digest(raw)) if raw is not None else None
        if actual!=expected:raise ValueError('Test source drift: '+name)
    rows=json.loads((root/'team/file-ownership.json').read_text(encoding='utf-8'))['files']
    selected=[];missing=[]
    for row in rows:
        name=row['path']
        if not name.startswith(('backend/','frontend/','infra/','scripts/','config/')) and name not in {'package.json','package-lock.json','requirements-dev.txt','.gitattributes','.gitignore','.github/workflows/ci.yml'}:continue
        if name in {'config/report-items.json','config/team-allocation.json'}:continue
        path=safe_file(root,name)
        if not path.is_file():missing.append(name);continue
        if path.suffix not in SUFFIXES and path.name!='Dockerfile':continue
        if '.live.' in name or '.private.' in name or name.endswith(('config.js','.pem','.key')):raise ValueError('Private/live source cannot enter public manifest: '+name)
        raw=path.read_bytes();raw.decode('utf-8-sig')
        if b'\0' in raw:raise ValueError('Binary deployment source')
        selected.append((name,source_digest(raw)))
    hashes=dict(sorted(selected));snapshot=digest(json.dumps(hashes,sort_keys=True,separators=(',',':')).encode())
    head=subprocess.run(['git','-c','safe.directory='+root.as_posix(),'rev-parse','HEAD'],cwd=root,capture_output=True,text=True)
    native_local=results['scope']=='LOCAL_REPOSITORY' and results['passed'] is True
    return {'schema':1,'version':json.loads((root/'package.json').read_text(encoding='utf-8'))['version'],
            'created_at':datetime.now(timezone.utc).isoformat(),'base_commit':head.stdout.strip() if head.returncode==0 else None,
            'working_tree':True,'manifest_scope':'TV4_SOURCE_REVIEW','fingerprint_format':'UTF8_LF_SHA256','source_snapshot_sha256':snapshot,'files':hashes,
            'tests':{k:results[k] for k in ('recorded_at','scope','passed','tests_run') if k in results},
            'test_covered_files':covered,'missing_source_files':sorted(missing),
            'ready_for_native_review':native_local and not missing,'aws_deployed':False,'aws_verified_for_this_release':False,
            'deployment_target':None,'configuration_scope':'Public source/example files only; live IAM, gates, prices, inventory and budget are not read here.',
            'blockers':(['Repository modules are not integrated'] if missing else [])+
                       (['TV4 unit result used explicit support sources'] if not native_local else [])+
                       ['Fresh account/Region/inventory/budget and IAM/change-set review','Native lifecycle/data acceptance and release approval'],
            'rollback':'Keep compatible schema-2 workers and active operation generations. Do not reset ledger, refund unknown reservations or delete user data for a code rollback.'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--results',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();value=prepare(json.loads(a.results.read_text(encoding='utf-8')))
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'files':len(value['files']),'snapshot':value['source_snapshot_sha256'],
                      'missing_sources':len(value['missing_source_files']),'ready_for_native_review':value['ready_for_native_review'],'aws_deployed':False}))
if __name__=='__main__':main()
