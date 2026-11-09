// Called only by scripts/benchmark_workloads.py after live ownership/budget checks.
// One iteration = one application request, never a CloudHub management API call.
import http from 'k6/http';
import crypto from 'k6/crypto';
import {Counter} from 'k6/metrics';
const cfg=JSON.parse(open(__ENV.CLOUDHUB_BENCH_MANIFEST));
if(!cfg.isolated_validation||!/^env-[a-f0-9]{24}$/.test(cfg.environment_id)||!cfg.target||cfg.duration_s>3600||cfg.rate>100||cfg.rate*cfg.duration_s>10000)throw Error('Unreviewed target or load bounds');
const correctness=new Counter('cloudhub_correctness_failures');
export const options={scenarios:{measured:{executor:'constant-arrival-rate',rate:cfg.rate,timeUnit:'1s',duration:cfg.duration_s+'s',preAllocatedVUs:cfg.concurrency,maxVUs:cfg.concurrency}},
 thresholds:{dropped_iterations:['count==0'],http_req_failed:['rate<=0.1'],cloudhub_correctness_failures:['count==0']},
 maxRedirects:0,userAgent:'CloudHub-Isolated-Benchmark/1',discardResponseBodies:false};
export function setup(){
 // Warmup is explicitly separate from measured iterations. No random cache
 // busting, fixed CloudFront IPs, Origin Shield or Lambda@Edge load tests.
 const end=Date.now()+cfg.warmup_s*1000;
 while(Date.now()<end)http.get(cfg.target,{redirects:0,timeout:'5s',responseType:'binary',headers:headers()});
 console.log(JSON.stringify({cloudhub_measurement_start:Math.floor(Date.now()/1000)}));
}
export function teardown(){console.log(JSON.stringify({cloudhub_measurement_end:Math.floor(Date.now()/1000)}));}
function headers(){return cfg.template_id==='T09'?{Authorization:'Bearer '+__ENV.CLOUDHUB_BENCH_TOKEN}:{};}
export default function(){
 const started=Date.now(),response=http.get(cfg.target,{redirects:0,timeout:'5s',responseType:'binary',headers:headers()});
 const correct=response.status===200&&crypto.sha256(response.body,'hex')===cfg.expected_sha256;
 if(cfg.template_id==='T02')console.log(JSON.stringify({cloudhub_cache:{pop:response.headers['X-Amz-Cf-Pop']||null,x_cache:response.headers['X-Cache']||null}}));
 if(!correct)correctness.add(1);else correctness.add(0);
 console.log(JSON.stringify({cloudhub_observation:{elapsed_ms:Date.now()-started,ok:response.status===200,bytes:response.body?.byteLength||0,correct}}));
}
export function handleSummary(data){return {'summary.json':JSON.stringify(data,null,2)};}
