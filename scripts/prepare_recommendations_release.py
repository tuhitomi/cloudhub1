"""Prepare a selective F03 patch from an exported native template and ZIP.

LOCAL ONLY: writes private output artifacts, never calls AWS. Export inputs
outside Git; the native template may contain origin protection configuration.
Review/execute a CloudFormation change set through the existing deployment flow.
"""
import argparse,hashlib,io,json,zipfile
from copy import deepcopy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
MODULES=('api','runtime','service','quotes','lifecycle','ledger','cost','operating_policy','workloads','workload_cost','recommendations','benchmarks','benchmark_agent')
ROUTES=(('GET','/recommendations/schema',5,10),('POST','/recommendations',2,4),('GET','/admin/benchmarks',2,4),('POST','/admin/benchmarks',1,2),('POST','/admin/benchmarks/{benchmark_id}/{control}',1,2))
def prepare(before,code,bucket,policy):
    target=deepcopy(before);resources=target['Resources']
    if resources['ApiFunction']['Type']!='AWS::Lambda::Function':raise ValueError('Use the exported native CloudFormation template; do not replace the stack with a new generated template')
    if 'RecommendationsEnabled' in target['Parameters']:raise ValueError('Already integrated: update the existing deployment, do not create duplicate routes')
    originals=zipfile.ZipFile(io.BytesIO(code));patches={'cloudhub/'+n+'.py':(ROOT/'backend/cloudhub'/ (n+'.py')).read_bytes() for n in MODULES}
    patches['cloudhub/benchmark-scenarios.json']=(ROOT/'backend/cloudhub/benchmark-scenarios.json').read_bytes()
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as result:
        for name in sorted(set(originals.namelist())|set(patches)):
            info=zipfile.ZipInfo(name,date_time=(2026,10,18,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o644<<16
            result.writestr(info,patches[name] if name in patches else originals.read(name))
    blob=output.getvalue();digest=hashlib.sha256(blob).hexdigest();key='releases/recommendations/'+digest+'/backend.zip'
    target['Parameters'].update(RecommendationsEnabled={'Type':'String','Default':'false','AllowedValues':['true','false']},BenchmarksBucket={'Type':'String','Default':bucket},RecommendationPolicyJson={'Type':'String','Default':json.dumps(policy,separators=(',',':'))})
    for name in ['ApiFunction','WorkerFunction','SweepFunction','ExpiryFunction']:resources[name]['Properties']['Code']={'S3Bucket':bucket,'S3Key':key}
    resources['ApiFunction']['Properties']['Environment']['Variables'].update(RECOMMENDATIONS_ENABLED={'Ref':'RecommendationsEnabled'},BENCHMARK_BUCKET={'Ref':'BenchmarksBucket'},RECOMMENDATION_POLICY_JSON={'Ref':'RecommendationPolicyJson'})
    paths=resources['HttpApi']['Properties']['Body']['paths'];base=paths['/templates']['get']
    if not base.get('security'):raise ValueError('Authenticated source route required')
    settings=resources['HttpApiApiGatewayDefaultStage']['Properties'].setdefault('RouteSettings',{})
    for i,(method,path,rate,burst) in enumerate(ROUTES):
        if method.lower() in paths.get(path,{}):raise ValueError('Route already managed: '+path)
        paths.setdefault(path,{})[method.lower()]=deepcopy(base)
        if '{benchmark_id}' in path:paths[path][method.lower()]['parameters']=[{'name':n,'in':'path','required':True,'schema':{'type':'string'}} for n in ['benchmark_id','control']]
        permission=deepcopy(resources['ApiFunctionRoute0Permission'])
        permission['Properties']['SourceArn']['Fn::Sub'][0]='arn:${AWS::Partition}:execute-api:${AWS::Region}:${AWS::AccountId}:${__ApiId__}/${__Stage__}/'+method+path.replace('{benchmark_id}','*').replace('{control}','*')
        resources['ApiFunctionRecommendation'+str(i)+'Permission']=permission;settings[method+' '+path]={'ThrottlingRateLimit':rate,'ThrottlingBurstLimit':burst}
    allowed={'ApiFunction','WorkerFunction','SweepFunction','ExpiryFunction','HttpApi','HttpApiApiGatewayDefaultStage'}|{'ApiFunctionRecommendation'+str(i)+'Permission' for i in range(5)}
    if any(v!=resources[k] for k,v in before['Resources'].items() if k not in allowed):raise ValueError('Unrelated native resource changed')
    return target,blob,{'backend_sha256':digest,'code_bucket':bucket,'code_key':key,'modified_resources':sorted(allowed),'new_iam_privileges':[],
        'gate_initial':'false','rollback':'Close admission, retain workload-aware workers for new records; do not reset ledger or restore old workers over new workload data.'}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--before-template',type=Path,required=True);p.add_argument('--before-code',type=Path,required=True);p.add_argument('--artifact-bucket',required=True);p.add_argument('--policy',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.resolve().is_relative_to(ROOT):p.error('Private deployment output must stay outside the repository')
    template,blob,review=prepare(json.loads(a.before_template.read_text(encoding='utf-8')),a.before_code.read_bytes(),a.artifact_bucket,json.loads(a.policy.read_text(encoding='utf-8')))
    a.out.mkdir(parents=True,exist_ok=True);(a.out/'backend.zip').write_bytes(blob);(a.out/'template.private.json').write_text(json.dumps(template,indent=2),encoding='utf-8');(a.out/'review.json').write_text(json.dumps(review,indent=2),encoding='utf-8');print(json.dumps(review))
if __name__=='__main__':main()
