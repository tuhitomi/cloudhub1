"""Reproducible LOCAL checks. AWS SDK transport is blocked throughout unit tests."""
import argparse,ast,contextlib,io,json,logging,os,re,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'tests'),str(ROOT.parents[1]/'work/deps')]

def run():
    from check_tv4 import required_files
    missing=[name for name in required_files(ROOT) if not (ROOT/name).is_file()]
    if missing:
        return {'recorded_at':datetime.now(timezone.utc).isoformat(),'mode':'LOCAL_ONLY','passed':False,
                'status':'BLOCKED_MISSING_DEPENDENCIES','missing_files':missing,'checks':[],
                'aws_resources_created':0,'aws_deployments':0,
                'limits':['Integrate peer modules before full-repository validation; use check_tv4.py only with explicitly labelled support sources.']}
    os.environ['AWS_EC2_METADATA_DISABLED']='true'
    temp=ROOT.parents[1]/'work/product-check-tmp';temp.mkdir(parents=True,exist_ok=True)
    tempfile.tempdir=str(temp);os.environ.update(TEMP=str(temp),TMP=str(temp))
    checks=[]
    sources=[*ROOT.joinpath('backend').rglob('*.py'),*ROOT.joinpath('scripts').glob('*.py'),*ROOT.joinpath('tests').glob('*.py')]
    for p in sources:ast.parse(p.read_text(encoding='utf-8-sig'),str(p))
    checks.append({'name':'python_syntax','passed':True,'files':len(sources)})
    logging.disable(logging.CRITICAL);buf=io.StringIO()
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern='test_*.py')
    with patch('botocore.httpsession.URLLib3Session.send',side_effect=AssertionError('AWS transport is prohibited in LOCAL tests')),contextlib.redirect_stdout(buf):
        result=unittest.TextTestRunner(stream=buf,verbosity=1).run(suite)
    checks.append({'name':'python_LOCAL_mock_stubber','passed':result.wasSuccessful(),'count':result.testsRun,
        'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
        'failure_details':[str(t)+': '+e[-1800:] for t,e in result.failures+result.errors]})
    os.environ['CLOUDHUB_TEST_PYTHON']=sys.executable
    node=subprocess.run(['node','--test','--test-reporter=tap',*map(str,sorted(ROOT.joinpath('tests').glob('*.test.mjs')))],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
    counts={k:int(v) for k,v in re.findall(r'^# (tests|pass|fail|skipped) (\d+)',node.stdout,re.M)}
    checks.append({'name':'frontend_LOCAL_DOM_mock','passed':node.returncode==0,**counts,
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
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    result=run();args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False));raise SystemExit(0 if result['passed'] else 1)
