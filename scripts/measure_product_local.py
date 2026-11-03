"""Separate acceptance and infrastructure simulation latency. Never an AWS SLA."""
import argparse,json,sys,time
from pathlib import Path
from statistics import median
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'tests')]
from test_quotes_continuous import QuoteTests

def percentile(values,q):
    values=sorted(values)
    return values[min(len(values)-1,max(0,__import__('math').ceil(len(values)*q)-1))] if values else None

def measure(count=30):
    all_requests=[];accepted=[];ready=[];errors=[]
    for _ in range(count):
        fixture=QuoteTests();fixture.setUp();body=fixture.quoted()
        t=time.perf_counter()
        try:
            op=fixture.s.create('alice','measure-key',body)
            accepted.append((time.perf_counter()-t)*1000)
            start=time.perf_counter();fixture.finish(op)
            ready.append((time.perf_counter()-start)*1000)
        except Exception as e:errors.append(type(e).__name__)
        finally:all_requests.append((time.perf_counter()-t)*1000)
    return {'mode':'LOCAL_MEMORY_AND_DRIVER_DOUBLE','requests':count,'errors':len(errors),'error_types':errors,
            'error_rate':len(errors)/count,'throttles':0,'throttles_scope':'No AWS service was called; zero is not AWS throttle evidence',
            'acceptance_ms_success_only':{'p50':median(accepted) if accepted else None,'p95':percentile(accepted,.95),'max':max(accepted) if accepted else None},
            'infrastructure_simulation_ms_success_only':{'p50':median(ready) if ready else None,'p95':percentile(ready,.95),'max':max(ready) if ready else None},
            'all_attempts_total_ms':{'p95':percentile(all_requests,.95),'max':max(all_requests)},
            'is_aws_sla_proof':False,'not_measured':['Cognito','DynamoDB network','SSM','Lambda cold starts','real infrastructure creation','real user concurrency']}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    args.out.write_text(json.dumps(measure(),indent=2)+'\n',encoding='utf-8');print('Local timing only; not AWS performance evidence.')
