"""Run TV4 unit/SDK regressions offline, with explicit dependency and fixture scope."""
import argparse,contextlib,hashlib,importlib.util,io,json,logging,os,socket,sys,tempfile,unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
HELPERS=('scripts/generate_infra.py','scripts/migrate_forecast_ledger.py','scripts/aws_lifecycle.py',
         'tests/test_domain.py','tests/test_processors.py','tests/test_quotes_continuous.py','tests/test_s3.py')

def registry(root):
    return json.loads((root/'team/file-ownership.json').read_text(encoding='utf-8'))['files']

def required_files(root):
    return sorted({row['path'] for row in registry(root) if row['path'].startswith('backend/') and row['path'].endswith('.py')}|set(HELPERS))

def covered_files(root):
    return {row['path']:hashlib.sha256((root/row['path']).read_bytes()).hexdigest() for row in registry(root)
            if row['owner']=='TV4' and (row['path'].startswith(('backend/','tests/')) or row['path'] in {'scripts/check_tv4.py','infra/lifecycle.asl.json'})
            and (root/row['path']).is_file()}

def assemble(root,support,destination):
    additions=[]
    for row in registry(root):
        name=row['path'];rel=Path(name)
        if rel.is_absolute() or '..' in rel.parts or '.git' in rel.parts:raise ValueError('Unsafe registry path')
        current=root/name;source=current if current.is_file() else support/name
        if not current.is_file() and row['owner']=='TV4':continue
        if not source.is_file():continue
        allowed=root if current.is_file() else support
        if source.is_symlink() or not source.resolve().is_relative_to(allowed.resolve()):raise ValueError('Unsafe support source')
        raw=source.read_bytes();raw.decode('utf-8-sig')
        if b'\0' in raw:raise ValueError('Binary support source')
        target=destination/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        if not current.is_file():additions.append({'path':name,'owner':row['owner'],'sha256':hashlib.sha256(raw).hexdigest()})
    return additions

def run(root=ROOT,support=None,deps=None):
    root=Path(root).resolve();missing=[name for name in required_files(root) if not (root/name).is_file()]
    common={'recorded_at':datetime.now(timezone.utc).isoformat(),'aws_calls':0,'aws_sdk_transport':'BLOCKED',
            'full_product_acceptance':False,'covered_files':covered_files(root)}
    if missing and support is None:
        return {**common,'status':'BLOCKED_MISSING_DEPENDENCIES','passed':False,'scope':'LOCAL_REPOSITORY',
                'missing_files':missing,'tests_run':0,'reason':'Integrate TV2/TV3 modules before native repository regressions; optional --support-source is a separately labelled local fixture.'}
    temp_base=Path(tempfile.gettempdir()).resolve()
    with tempfile.TemporaryDirectory(prefix='cloudhub-tv4-',dir=temp_base) as folder:
        temporary=Path(folder).resolve()
        if not temporary.is_relative_to(temp_base):raise ValueError('Temporary workspace escaped its parent')
        additions=[];workspace=root
        if missing:
            support=Path(support).resolve();workspace=temporary/'source';workspace.mkdir()
            additions=assemble(root,support,workspace)
            unresolved=[name for name in required_files(root) if not (workspace/name).is_file()]
            if unresolved:return {**common,'status':'BLOCKED_MISSING_DEPENDENCIES','passed':False,'scope':'LOCAL_SUPPORT_FIXTURE',
                                  'missing_files':unresolved,'tests_run':0,'support_files':additions}
        sys.path[:0]=[str(workspace/'backend'),str(workspace/'tests'),str(workspace/'scripts')]
        if deps:sys.path.insert(0,str(Path(deps).resolve()))
        if importlib.util.find_spec('boto3') is None:
            return {**common,'status':'BLOCKED_TEST_DEPENDENCY','passed':False,'scope':'LOCAL_SUPPORT_FIXTURE' if additions else 'LOCAL_REPOSITORY',
                    'tests_run':0,'reason':'Install requirements-dev.txt, or select the existing local SDK directory with --deps.'}
        os.environ.update(AWS_EC2_METADATA_DISABLED='true',AWS_ACCESS_KEY_ID='local-test-only',AWS_SECRET_ACCESS_KEY='local-test-only',
                          AWS_DEFAULT_REGION='us-east-1',AWS_CONFIG_FILE=str(temporary/'empty-config'),
                          AWS_SHARED_CREDENTIALS_FILE=str(temporary/'empty-credentials'))
        for key in ('AWS_PROFILE','AWS_SESSION_TOKEN','AWS_WEB_IDENTITY_TOKEN_FILE','AWS_ROLE_ARN'):os.environ.pop(key,None)
        suites=sorted(Path(row['path']).stem for row in registry(root) if row['owner']=='TV4' and row['path'].startswith('tests/test_')
                      and row['path'].endswith('.py') and (root/row['path']).is_file())
        captured=io.StringIO();attempts=[]
        def forbidden(*args,**kwargs):
            attempts.append('blocked');raise AssertionError('Network transport is prohibited during LOCAL TV4 tests')
        prior_cwd=Path.cwd();logging.disable(logging.CRITICAL)
        try:
            os.chdir(workspace)
            with patch('botocore.httpsession.URLLib3Session.send',side_effect=forbidden),patch.object(socket.socket,'connect',forbidden),\
                 contextlib.redirect_stdout(captured),contextlib.redirect_stderr(captured):
                suite=unittest.defaultTestLoader.loadTestsFromNames(suites)
                result=unittest.TextTestRunner(stream=captured,verbosity=1).run(suite)
        finally:os.chdir(prior_cwd)
        success=result.wasSuccessful() and not result.skipped and not attempts
        return {**common,'status':'LOCAL_TV4_TESTS_PASSED' if success else 'LOCAL_TV4_TESTS_FAILED','passed':success,
                'scope':'LOCAL_SUPPORT_FIXTURE' if additions else 'LOCAL_REPOSITORY','tests_run':result.testsRun,
                'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
                'blocked_network_attempts':len(attempts),'suites':suites,'support_files':additions,
                'failure_details':[{'test':str(case),'last_line':trace.strip().splitlines()[-1][:400]} for case,trace in result.failures+result.errors],
                'limitations':['Unit/mock/SDK Stubber only; no AWS account, IAM, billing, load or restored production data was verified.',
                              'A support-fixture PASS does not mean all dependencies are present in the public repository.']}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--support-source',type=Path);p.add_argument('--deps',type=Path);p.add_argument('--out',type=Path)
    p.add_argument('--allow-missing-dependencies',action='store_true',help='Report BLOCKED without failing documentation-only CI; never turns it into PASS')
    a=p.parse_args();result=run(support=a.support_source,deps=a.deps)
    if a.out:a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    summary={k:v for k,v in result.items() if k not in {'covered_files','support_files','missing_files'}}
    summary['missing_count']=len(result.get('missing_files',[]));summary['support_file_count']=len(result.get('support_files',[]))
    print(json.dumps(summary,ensure_ascii=False))
    if result['passed']:return 0
    if result['status'].startswith('BLOCKED'):
        if a.allow_missing_dependencies:print('::notice::TV4 integration tests are BLOCKED, not PASS; inspect the JSON report.');return 0
        return 2
    return 1

if __name__=='__main__':raise SystemExit(main())
