"""Reproducible LOCAL checks. AWS SDK transport is blocked throughout unit tests."""
import argparse,ast,contextlib,io,ipaddress,json,logging,os,re,socket,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'tests')]


@contextlib.contextmanager
def offline_environment():
    """Use dummy credentials and allow only HTTP loopback fixtures, never AWS."""
    attempts=[];loopback=[]
    connect=socket.socket.connect;connect_ex=socket.socket.connect_ex;resolve=socket.getaddrinfo
    def forbidden(*args,**kwargs):
        attempts.append('BLOCKED_EXTERNAL_TRANSPORT')
        raise AssertionError('External network/AWS transport is prohibited in LOCAL tests')
    def checked_connect(original):
        def checked(sock,address,*args,**kwargs):
            try:allowed=ipaddress.ip_address(address[0]).is_loopback
            except (ValueError,TypeError,IndexError):allowed=False
            if not allowed:return forbidden()
            loopback.append('LOOPBACK_FIXTURE')
            return original(sock,address,*args,**kwargs)
        return checked
    def checked_resolve(host,*args,**kwargs):
        if host not in {'127.0.0.1','::1','localhost'}:return forbidden()
        return resolve(host,*args,**kwargs)
    with tempfile.TemporaryDirectory(prefix='cloudhub-local-validation-') as folder:
        environment=dict(os.environ,AWS_EC2_METADATA_DISABLED='true',AWS_ACCESS_KEY_ID='local-test-only',
            AWS_SECRET_ACCESS_KEY='local-test-only',AWS_DEFAULT_REGION='us-east-1',AWS_REGION='us-east-1',
            AWS_CONFIG_FILE=str(Path(folder)/'empty-config'),AWS_SHARED_CREDENTIALS_FILE=str(Path(folder)/'empty-credentials'))
        for key in ('AWS_PROFILE','AWS_SESSION_TOKEN','AWS_SECURITY_TOKEN','AWS_WEB_IDENTITY_TOKEN_FILE','AWS_ROLE_ARN',
                    'AWS_CONTAINER_CREDENTIALS_FULL_URI','AWS_CONTAINER_CREDENTIALS_RELATIVE_URI'):
            environment.pop(key,None)
        with patch.dict(os.environ,environment,clear=True),patch.object(tempfile,'tempdir',folder),\
             patch('botocore.httpsession.URLLib3Session.send',side_effect=forbidden),\
             patch.object(socket.socket,'connect',checked_connect(connect)),\
             patch.object(socket.socket,'connect_ex',checked_connect(connect_ex)),patch.object(socket,'getaddrinfo',checked_resolve):
            yield attempts,loopback

def run():
    from check_tv4 import required_files
    missing=[name for name in required_files(ROOT) if not (ROOT/name).is_file()]
    if missing:
        return {'recorded_at':datetime.now(timezone.utc).isoformat(),'mode':'LOCAL_ONLY','passed':False,
                'status':'BLOCKED_MISSING_DEPENDENCIES','missing_files':missing,'checks':[],
                'aws_resources_created':0,'aws_deployments':0,
                'limits':['Integrate peer modules before full-repository validation; use check_tv4.py only with explicitly labelled support sources.']}
    with offline_environment() as (attempts,loopback):
        result=_run_checks()
    result.update(scope='LOCAL_REPOSITORY',support_file_count=0,aws_calls=0,
                  blocked_external_network_attempts=len(attempts),loopback_fixture_connections=len(loopback))
    result['passed']=result['passed'] and not attempts
    return result


def _run_checks():
    checks=[]
    sources=[*ROOT.joinpath('backend').rglob('*.py'),*ROOT.joinpath('scripts').glob('*.py'),*ROOT.joinpath('tests').glob('*.py')]
    for p in sources:ast.parse(p.read_text(encoding='utf-8-sig'),str(p))
    checks.append({'name':'python_syntax','passed':True,'files':len(sources)})
    logging.disable(logging.CRITICAL);buf=io.StringIO()
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern='test_*.py')
    with contextlib.redirect_stdout(buf):
        result=unittest.TextTestRunner(stream=buf,verbosity=1).run(suite)
    checks.append({'name':'python_LOCAL_mock_stubber','passed':result.wasSuccessful() and result.testsRun>0 and not result.skipped,'count':result.testsRun,
        'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
        'failure_details':[str(t)+': '+e[-1800:] for t,e in result.failures+result.errors]})
    os.environ['CLOUDHUB_TEST_PYTHON']=sys.executable
    node=subprocess.run(['node','--test','--test-reporter=tap',*map(str,sorted(ROOT.joinpath('tests').glob('*.test.mjs')))],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
    counts={k:int(v) for k,v in re.findall(r'^# (tests|pass|fail|skipped) (\d+)',node.stdout,re.M)}
    checks.append({'name':'frontend_LOCAL_DOM_mock','passed':node.returncode==0 and counts.get('tests',0)>0 and not counts.get('skipped',0),**counts,
        'failure_details':[] if node.returncode==0 else [node.stdout[-4000:],node.stderr[-1000:]]})
    try:
        from openapi_spec_validator import validate
        validate(json.loads((ROOT/'docs/openapi.json').read_text(encoding='utf-8')))
        checks.append({'name':'openapi_schema','passed':True})
    except Exception as error:checks.append({'name':'openapi_schema','passed':False,'error':str(error)[:2000]})
    from validate_locales import validate as validate_locales
    checks.append({'name':'existing_locale_packs','passed':True,**validate_locales()})
    try:
        from cfnlint.api import lint
        from generate_infra import build_template
        from cloudhub.s3_template import s3_template
        from cloudhub.catalog import configuration_profiles
        documents=[('control',build_template()),('control_external',build_template('https://app.example.com/')),
                   ('control_shared',build_template(shared_edge={'id':'EEXAMPLE','domain':'example.cloudfront.net'}))]
        for tid in ['T02','T07']:
            for profile in ['standard','files']:
                cfg=next(x['configuration'] for x in configuration_profiles(tid) if x['id']==profile)
                env={'environment_id':'env-'+'a'*24,'owner_id':'local','template_id':tid,'configuration':cfg,'direct_upload_schema':1}
                documents.append((tid+'_'+profile,s3_template(env,{'account_id':'123456789012','region':'us-east-1'})))
        for name,doc in documents:
            errors=lint(json.dumps(doc),regions=['us-east-1'])
            blocking=[x for x in errors if x.rule.id.startswith('E') or x.rule.id=='W3037']
            checks.append({'name':'cfn_lint_'+name,'passed':not blocking,'blocking':[x.rule.id+': '+x.message for x in blocking],
                           'warnings':[x.rule.id+': '+x.message for x in errors if x not in blocking]})
    except Exception as error:checks.append({'name':'cfn_lint','passed':False,'error':repr(error)})
    return {'recorded_at':datetime.now(timezone.utc).isoformat(),'timezone':'Asia/Bangkok','mode':'LOCAL_ONLY',
        'passed':all(x['passed'] for x in checks),'checks':checks,'aws_resources_created':0,'aws_deployments':0,
        'aws_native_validation':'NOT_PART_OF_LOCAL_RUN','physical_mobile_tested':False,'aws_load_tested':False,
        'limits':['DOM tests do not prove visual quality or real service permissions.','This LOCAL runner does not inspect AWS lifecycle, credits or billing; use separate native evidence.']}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--deps',type=Path,help='Optional existing LOCAL dependency directory; normally install requirements-dev.txt')
    args=p.parse_args()
    if args.deps:sys.path.insert(0,str(args.deps.resolve()))
    result=run();args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False));raise SystemExit(0 if result['passed'] else 1)
