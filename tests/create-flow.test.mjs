import {setLanguage} from '../frontend/i18n.js';
await setLanguage('vi',{persist:false});
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createCreationFlow,validateCreation} from '../frontend/create-flow.js';
import {createJournal} from '../frontend/create-journal.js';
const template={template_id:'T01',name:'Máy Linux',create_enabled:true,operating_capabilities:{ending_policies:['BACKUP_RETIRE','PAUSE']}};
const quote=request=>({approved:true,total_milliusd:454,budget_feasible:true,...request,first_period:{total_milliusd:350},renewal_period:{total_milliusd:200},after_shutdown:{total_milliusd:104},preview:{total_milliusd:500}});
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
const configured={...template,configuration_options:[{id:'standard',configuration:{data_gib:8},create_enabled:true},{id:'expanded',configuration:{data_gib:16},create_enabled:true}]};
const regional={...configured,default_region:'ap-southeast-1',regions:[{region:'ap-southeast-1',status:'SUPPORTED',configuration_options:configured.configuration_options},{region:'ap-northeast-1',status:'SUPPORTED',configuration_options:[configured.configuration_options[0]]},{region:'us-east-1',status:'UNAVAILABLE',configuration_options:configured.configuration_options.map(p=>({...p,create_enabled:false}))}]};

test('reviewed application selection binds the fresh quote and changing title clears consent',async()=>{
 const appTemplate={...regional,template_id:'T03',application_options:{'ap-southeast-1':[{release_id:'content-site-1',revision:'a'.repeat(64),enabled:true},{release_id:'content-site-2',revision:'b'.repeat(64),enabled:false}]}};
 const {flow,calls}=setup();flow.open(appTemplate);flow.change({appRelease:'content-site-1',appTitle:'My website'});await review(flow);assert.equal(flow.snapshot().quote.application.title,'My website');flow.change({appTitle:'Changed website'});assert.equal(flow.snapshot().quote,null);assert.equal(flow.snapshot().consent,false);await review(flow);await flow.submit();assert.equal(calls[0].body.application.title,'Changed website');
 flow.open(appTemplate);flow.change({appRelease:'content-site-2',appTitle:'Closed release'});assert.equal(flow.snapshot().canNext,false);await flow.next();assert.equal(flow.snapshot().step,0);
});

test('application identity missing from a quote cannot be confirmed',async()=>{
 const appTemplate={...regional,template_id:'T03',application_options:{'ap-southeast-1':[{release_id:'content-site-1',revision:'a'.repeat(64),enabled:true}]}};
 const {flow}=setup({estimate:async body=>{const result=quote(body);delete result.application;return result;}});flow.open(appTemplate);flow.change({appRelease:'content-site-1',appTitle:'My website'});await flow.next();await flow.next();assert.equal(flow.snapshot().quoteStatus,'error');assert.equal(flow.snapshot().canNext,false);
});

test('application release proof on standard never permits expanded',()=>{
 const appTemplate={...regional,template_id:'T03',application_options:{'ap-southeast-1':[{release_id:'content-site-1',revision:'a'.repeat(64),enabled:true,configuration_ids:['standard']}]}};
 const {flow}=setup();flow.open(appTemplate);flow.change({appRelease:'content-site-1',appTitle:'My website'});assert.equal(flow.snapshot().canNext,true);flow.change({configurationId:'expanded'});assert.equal(flow.snapshot().canNext,false);assert.ok(flow.snapshot().errors.appRelease);
});
test('continuous capability follows the exact selected configuration',()=>{
 const scoped=structuredClone(regional);scoped.regions[0].operating_modes=['AUTO_OFF','AUTO_RENEW','CONTINUOUS'];
 scoped.regions[0].configuration_options[0].operating_modes=['AUTO_OFF','AUTO_RENEW','CONTINUOUS'];scoped.regions[0].configuration_options[1].operating_modes=['AUTO_OFF','AUTO_RENEW'];
 const {flow}=setup();flow.open(scoped);flow.change({mode:'CONTINUOUS'});assert.equal(flow.snapshot().errors.mode,undefined);
 flow.change({configurationId:'expanded'});assert.ok(flow.snapshot().errors.mode);assert.ok(!flow.snapshot().template.operating_capabilities.modes.includes('CONTINUOUS'));
});
test('changing Region clears old consent, incompatible package and a late estimate',async()=>{
 const pending=deferred();let calls=0;const {flow}=setup({estimate:body=>++calls===1?pending.promise:Promise.resolve(quote(body))});flow.open(regional);flow.change({configurationId:'expanded'});await flow.next();const first=flow.next();flow.change({region:'ap-northeast-1'});assert.equal(flow.snapshot().form.configurationId,'standard');assert.equal(flow.snapshot().consent,false);await flow.next();await flow.next();pending.resolve(quote({region:'ap-southeast-1'}));await first;assert.equal(flow.snapshot().quote.region,'ap-northeast-1');
});
test('Region is forwarded to create and restored Region is immutable',async()=>{
 const {flow,calls}=setup();flow.open(regional);flow.change({region:'ap-northeast-1'});await review(flow);await flow.submit();assert.equal(calls[0].body.region,'ap-northeast-1');
 flow.open(regional,'rp-test',{data_gib:8},'ap-northeast-1');flow.change({region:'ap-southeast-1'});assert.equal(flow.snapshot().form.region,'ap-northeast-1');
});
test('unsupported Region configuration stays noncreatable and unknown Region is invalid',async()=>{
 const {flow}=setup();flow.open(regional);flow.change({region:'us-east-1'});await flow.next();await flow.next();assert.equal(flow.snapshot().canNext,false);assert.equal(flow.snapshot().canSubmit,false);assert.ok(validateCreation({...flow.snapshot().form,region:'eu-west-1'},regional).region);
});
test('resource choice reaches quote/create and changing it clears consent and old prices',async()=>{let estimates=[];const {flow,calls}=setup({estimate:async body=>{estimates.push(body);return quote(body);}});flow.open(configured);flow.change({configurationId:'expanded'});await review(flow);assert.equal(estimates[0].configuration.data_gib,16);flow.change({configurationId:'standard'});assert.equal(flow.snapshot().consent,false);assert.equal(flow.snapshot().quote,null);await review(flow);await flow.submit();assert.equal(calls[0].body.configuration.data_gib,8);});
test('changed resource quote cannot be used for a different resource configuration',async()=>{const {flow}=setup({estimate:async body=>({...quote(body),configuration:{data_gib:8}})});flow.open(configured);flow.change({configurationId:'expanded'});await flow.next();await flow.next();assert.equal(flow.snapshot().canNext,false);assert.match(flow.snapshot().error,/không khớp cấu hình tài nguyên/);});
test('unverified configuration quote remains viewable but cannot create',async()=>{const {flow}=setup({estimate:async body=>({...quote(body),configuration_verified:false})});flow.open(configured);flow.change({configurationId:'expanded'});await flow.next();await flow.next();assert.equal(flow.snapshot().quoteStatus,'ready');assert.equal(flow.snapshot().canNext,false);assert.match(flow.snapshot().error,/chờ kiểm chứng AWS/);});
test('restore configuration is selected from source and stays locked',()=>{const {flow}=setup();flow.open(configured,'rp-local',{data_gib:16});flow.change({configurationId:'standard'});assert.equal(flow.snapshot().form.configurationId,'expanded');assert.equal(flow.snapshot().configurationLocked,true);assert.throws(()=>flow.open(configured,'rp-local',{data_gib:32}),/chưa có trong danh mục/);});
function setup(overrides={}){let clock=100,keys=new Map(),calls=[],accepted=[];const flow=createCreationFlow({estimate:async body=>quote(body),create:async(body,key)=>{calls.push({body,key});return {operation_id:'op-local'};},costAllowed:q=>!!q?.approved&&q.budget_feasible!==false,keyFor:scope=>{if(!keys.has(scope))keys.set(scope,'key-'+keys.size);return keys.get(scope);},forgetKey:scope=>keys.delete(scope),now:()=>clock,onAccepted:op=>accepted.push(op),...overrides});flow.open(template);return {flow,calls,accepted,advance:n=>clock+=n};}
async function review(flow){await flow.next();await flow.next();await flow.next();flow.consent(true);assert.equal(flow.snapshot().step,3);}
test('explicit auto off default; horizon independent from period; new template gate closed',()=>{const {flow}=setup();flow.change({estimateHours:'8',periodMinutes:'5',owner_id:'mallory',role:'admin'});assert.equal(flow.snapshot().form.mode,'AUTO_OFF');assert.equal(flow.snapshot().form.owner_id,undefined);assert.throws(()=>flow.open({...template,create_enabled:false}),/chưa được mở/);});
test('budget precision and pause capability validated without trusting UI',()=>{for(const budgetUsd of ['','-1','0','1e5','Infinity','1.0001'])assert.ok(validateCreation({estimateHours:'1',mode:'AUTO_RENEW',periodMinutes:'5',endingPolicy:'PAUSE',budgetUsd},template).budgetUsd);assert.ok(validateCreation({estimateHours:'1',mode:'AUTO_OFF',periodMinutes:'5',endingPolicy:'PAUSE',budgetUsd:'bad'},{template_id:'T02',operating_capabilities:{ending_policies:['BACKUP_RETIRE']}}).endingPolicy);});
test('no estimate request before mode selected, consent bound to current configuration',async()=>{let estimates=0;const {flow}=setup({estimate:async body=>{estimates++;return quote(body);}});assert.equal(estimates,0);await review(flow);assert.equal(flow.snapshot().canSubmit,true);flow.change({budgetUsd:'11',mode:'AUTO_RENEW'});assert.equal(flow.snapshot().consent,false);assert.equal(flow.snapshot().quote,null);assert.equal(flow.snapshot().step,1);await flow.submit();assert.equal(estimates,1);});
test('late quote ignored after configuration edits',async()=>{const wait=deferred();const {flow}=setup({estimate:()=>wait.promise});await flow.next();const pending=flow.next();assert.equal(flow.snapshot().quoteStatus,'loading');flow.change({periodMinutes:'5'});wait.resolve(quote({template_id:'T01',estimate_hours:1,operating_policy:{mode:'AUTO_OFF',period_minutes:60,ending_policy:'BACKUP_RETIRE',budget_limit_milliusd:null,confirmed:true}}));await pending;assert.equal(flow.snapshot().quote,null);assert.equal(flow.snapshot().quoteStatus,'idle');});
test('cancel and reopen fence old responses even for identical values',async()=>{const wait=deferred();const {flow}=setup({estimate:()=>wait.promise});await flow.next();const pending=flow.next();flow.cancel();flow.open(template);wait.reject(Error('old connection failure'));await pending;assert.equal(flow.snapshot().quoteStatus,'idle');assert.equal(flow.snapshot().error,'');});
test('quota and cumulative cap refusal cannot advance to confirmation',async()=>{const {flow}=setup({costAllowed:()=>false});await flow.next();await flow.next();await flow.next();assert.equal(flow.snapshot().step,2);assert.match(flow.snapshot().error,/Hạn mức/);assert.equal(flow.snapshot().canNext,false);flow.consent(true);assert.equal(flow.snapshot().consent,false);});
test('failed estimate clears prices, retry uses unchanged form',async()=>{let calls=0;const {flow}=setup({estimate:async body=>{if(++calls===1)throw Error('Giá tạm thời chưa có');return quote(body);}});flow.change({estimateHours:'8'});await flow.next();await flow.next();assert.equal(flow.snapshot().quoteStatus,'error');assert.equal(flow.snapshot().quote,null);await flow.loadQuote();assert.equal(flow.snapshot().quote.estimate_hours,8);assert.equal(flow.snapshot().quoteStatus,'ready');});
test('mismatched estimate policy blocked',async()=>{const {flow}=setup({estimate:async body=>({...quote(body),operating_policy:{...body.operating_policy,mode:'AUTO_RENEW'}})});await flow.next();await flow.next();assert.equal(flow.snapshot().quoteStatus,'error');assert.match(flow.snapshot().error,/không khớp/);});
test('policy object order does not reject the same API policy',async()=>{const {flow}=setup({estimate:async body=>({...quote(body),operating_policy:Object.fromEntries(Object.entries(body.operating_policy).reverse())})});await review(flow);assert.equal(flow.snapshot().canSubmit,true);});
test('unapproved pricing stays honest and cannot create',async()=>{const {flow}=setup({estimate:async body=>({...quote(body),approved:false,total_milliusd:null})});await flow.next();await flow.next();assert.equal(flow.snapshot().quoteStatus,'ready');assert.equal(flow.snapshot().canNext,false);assert.equal(flow.snapshot().canSubmit,false);});
test('60s old quote requires new review and consent before create',async()=>{const {flow,calls,advance}=setup();await review(flow);advance(60001);await flow.submit();assert.equal(calls.length,0);assert.equal(flow.snapshot().step,2);assert.equal(flow.snapshot().consent,false);});
test('periodic reconciliation exposes a retry after quote expires, without a disabled dead end',async()=>{const {flow,advance}=setup();await review(flow);advance(60001);flow.reconcile();assert.equal(flow.snapshot().step,2);assert.equal(flow.snapshot().quoteStatus,'error');assert.equal(flow.snapshot().consent,false);assert.match(flow.snapshot().error,/không còn hiệu lực/);await flow.loadQuote();assert.equal(flow.snapshot().canNext,true);});
test('double submit while pending sends one operation; closing blocked',async()=>{const wait=deferred();let creates=0;const {flow}=setup({create:()=>{creates++;return wait.promise;}});await review(flow);const pending=flow.submit();await flow.submit();assert.equal(creates,1);assert.equal(flow.cancel(),false);flow.change({periodMinutes:'5'});assert.equal(flow.snapshot().form.periodMinutes,'60');wait.resolve({operation_id:'op-local'});await pending;assert.equal(flow.snapshot().open,false);});
test('network uncertainty locks request; retry keeps body/key and permits recovery after quote age',async()=>{let requests=[];const {flow,advance}=setup({create:async(body,key)=>{requests.push({body,key});if(requests.length===1)throw Error('Mất kết nối');return {operation_id:'op-existing'};}});await review(flow);await flow.submit();assert.equal(flow.snapshot().uncertain,true);assert.equal(flow.cancel(),false);flow.change({estimateHours:'8'});advance(60001);await flow.submit();assert.deepEqual(requests[0],requests[1]);assert.equal(flow.snapshot().open,false);});
test('definite API rejection retains inputs and allows correcting form',async()=>{const {flow}=setup({create:async()=>{throw Object.assign(Error('Quota đã thay đổi'),{status:409});}});flow.change({estimateHours:'8'});await review(flow);await flow.submit();assert.equal(flow.snapshot().form.estimateHours,'8');assert.equal(flow.snapshot().uncertain,false);assert.equal(flow.snapshot().canCancel,true);flow.change({periodMinutes:'5'});assert.equal(flow.snapshot().form.periodMinutes,'5');});
test('accepted operation stays accepted if refresh callback fails',async()=>{const {flow}=setup({onAccepted:()=>{throw Error('list offline');}});await review(flow);await assert.rejects(()=>flow.submit(),/list offline/);assert.equal(flow.snapshot().open,false);assert.equal(flow.snapshot().uncertain,false);assert.equal(flow.snapshot().error,'');});
test('restore body includes recovery id only on create; never submits browser owner',async()=>{let estimates=[];const {flow,calls}=setup({estimate:async body=>{estimates.push(body);return quote(body);}});flow.open(template,'rp-local');await review(flow);await flow.submit();assert.equal(estimates[0].recovery_point,'rp-local');assert.equal(calls[0].body.recovery_point,'rp-local');assert.equal(calls[0].body.owner_id,undefined);});


test('continuous mode availability follows the selected Region without changing policy silently',()=>{
 const scoped=structuredClone(regional);scoped.regions[0].operating_modes=['AUTO_OFF','AUTO_RENEW','CONTINUOUS'];scoped.regions[1].operating_modes=['AUTO_OFF','AUTO_RENEW'];
 const {flow}=setup();flow.open(scoped);flow.change({mode:'CONTINUOUS'});assert.equal(flow.snapshot().errors.mode,undefined);
 flow.change({region:'ap-northeast-1'});assert.equal(flow.snapshot().form.mode,'CONTINUOUS');assert.ok(flow.snapshot().errors.mode);assert.equal(flow.snapshot().consent,false);
});

test('recommendation workload must match the fresh quote and is preserved on uncertain retry',async()=>{
 let attempts=[];const {flow,advance}=setup({create:async(body,key)=>{attempts.push({body,key});if(attempts.length===1)throw Error('offline');return {operation_id:'op-existing'};}});
 flow.setWorkload({data_mib:1024});await review(flow);await flow.submit();advance(60001);flow.setWorkload({data_mib:2048});await flow.submit();
 assert.deepEqual(attempts[0],attempts[1]);assert.equal(attempts[0].body.planning_workload.data_mib,1024);
 const mismatch=setup({estimate:async body=>({...quote(body),planning_workload:{data_mib:2048}})}).flow;mismatch.setWorkload({data_mib:1024});await mismatch.next();await mismatch.next();assert.equal(mismatch.snapshot().canNext,false);
});

test('reload recovers exactly the confirmed request/key after quote expiry, with fresh explicit consent',async()=>{
 const records=new Map(),storage={getItem:k=>records.get(k)||null,setItem:(k,v)=>records.set(k,v),removeItem:k=>records.delete(k)};
 let identity='pool/alice',attempts=[];
 const journal=createJournal({storage,owner:()=>identity});
 const first=setup({journal,create:async(body,key)=>{attempts.push({body,key});throw Error('response lost');}}).flow;
 first.open(regional);first.setWorkload({data_mib:2048});await review(first);await first.submit();assert.equal(first.snapshot().uncertain,true);assert.ok(journal.read());
 identity='pool/bob';const other=setup({journal}).flow;other.cancel();assert.equal(other.restorePending(),false);
 identity='pool/alice';const recovered=setup({journal,now:()=>9999999999999,create:async(body,key)=>{attempts.push({body,key});return {operation_id:'op-accepted-before-reload'};},keyFor:()=>{throw Error('must not generate a replacement key');}}).flow;
 recovered.cancel();assert.equal(recovered.restorePending(),true);assert.equal(recovered.snapshot().consent,false);assert.equal(recovered.snapshot().canCancel,false);
 assert.equal(attempts.length,1);await recovered.submit();assert.equal(attempts.length,1);
 recovered.consent(true);await recovered.submit();assert.deepEqual(attempts[0],attempts[1]);assert.equal(journal.read(),null);assert.equal(recovered.snapshot().open,false);
});

test('pending recovery gets a new quote review only after a definite backend quote rejection',async()=>{
 let saved;const journal={read:()=>saved,write:v=>saved=v,clear:()=>saved=null};
 const original=setup({journal,create:async()=>{throw Error('offline');}}).flow;await review(original);await original.submit();
 const flow=setup({journal,create:async()=>{throw Object.assign(Error('quote expired before acceptance'),{status:409,code:'QUOTE_EXPIRED'});}}).flow;
 flow.cancel();flow.restorePending();flow.consent(true);await flow.submit();assert.equal(saved,null);assert.equal(flow.snapshot().uncertain,false);assert.equal(flow.snapshot().step,2);assert.equal(flow.snapshot().consent,false);assert.equal(flow.snapshot().form.estimateHours,'1');
});

test('storage failure prevents sending a confirmed create; sign-out fences a late response',async()=>{
 let count=0;const blocked=setup({journal:{write:()=>{throw Error('storage denied');}},create:async()=>{count++;}}).flow;await review(blocked);await blocked.submit();assert.equal(count,0);assert.match(blocked.snapshot().error,/lưu trữ phiên/);
 const wait=deferred();let accepted=0;const flow=setup({create:()=>wait.promise,onAccepted:()=>accepted++}).flow;await review(flow);const pending=flow.submit();flow.reset();wait.resolve({operation_id:'op-old-owner'});await pending;assert.equal(accepted,0);assert.equal(flow.snapshot().open,false);
});

test('server expiry governs quote freshness after 60s; refresh never confirms changed prices',async()=>{
 let estimates=0;const {flow,advance,calls}=setup({estimate:async body=>({...quote(body),quote_id:'quote-'+(++estimates),quote_expires_at:estimates===1?120:240,total_milliusd:estimates===1?454:600})});
 await review(flow);advance(61000);assert.equal(flow.snapshot().canSubmit,true);await flow.reconcile({refresh:true});assert.equal(estimates,1);
 advance(44000);await flow.reconcile({refresh:true});assert.equal(estimates,2);assert.equal(flow.snapshot().consent,false);assert.equal(flow.snapshot().canSubmit,false);assert.equal(flow.snapshot().quote.total_milliusd,600);assert.match(flow.snapshot().quoteNotice,/xác nhận lại/);
 await flow.submit();assert.equal(calls.length,0);flow.consent(true);await flow.submit();assert.equal(calls[0].body.quote_id,'quote-2');
});
test('quote refresh coalesces pending requests and ignores a response after an input change',async()=>{
 const wait=deferred();let count=0;const {flow,advance}=setup({estimate:body=>++count===1?Promise.resolve(quote(body)):wait.promise});
 await review(flow);advance(46000);const pending=flow.reconcile({refresh:true});await flow.reconcile({refresh:true});assert.equal(count,2);assert.equal(flow.snapshot().consent,false);
 flow.change({estimateHours:'8'});wait.resolve(quote({estimate_hours:1}));await pending;assert.equal(flow.snapshot().quote,null);assert.equal(flow.snapshot().form.estimateHours,'8');
});
test('refresh errors retain form, require explicit retry and cannot create an API retry loop',async()=>{
 let count=0;const {flow,advance}=setup({estimate:async body=>{if(++count>1)throw Error('pricing unavailable');return quote(body);}});
 await review(flow);advance(46000);await flow.reconcile({refresh:true});assert.equal(flow.snapshot().step,2);assert.equal(flow.snapshot().quoteStatus,'error');assert.equal(flow.snapshot().form.periodMinutes,'60');assert.equal(flow.snapshot().consent,false);
 await flow.reconcile({refresh:true});assert.equal(count,2);
});
test('automatic quote refresh never replaces a request with an uncertain acceptance outcome',async()=>{
 let count=0,attempts=[];const {flow,advance}=setup({estimate:async body=>{count++;return quote(body);},create:async(body,key)=>{attempts.push({body,key});if(attempts.length===1)throw Error('lost response');return {operation_id:'op-original'};}});
 await review(flow);await flow.submit();advance(180000);await flow.reconcile({refresh:true});assert.equal(count,1);await flow.submit();assert.deepEqual(attempts[0],attempts[1]);
});
