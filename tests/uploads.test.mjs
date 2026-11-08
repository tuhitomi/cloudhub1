import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createUploader} from '../frontend/uploads.js';
import {createCreationFlow,creationRequest} from '../frontend/create-flow.js';

const session=()=>{const values=new Map();return {getItem:k=>values.get(k),setItem:(k,v)=>values.set(k,v)};};
test('reload resumes an accepted completion with the original key and no persisted capability',async()=>{
 const storage=session(),calls=[];let sends=0,completed=0,keys=0;
 const options={storage,now:()=>1000,keyFor:()=>String(++keys),post:async(path,body,key)=>{calls.push({path,key});if(path.endsWith('/complete')){if(++completed===1)throw Error('lost reply');return {operation_id:'op-original'};}return {upload_id:'upload-one',expires_at:120,complete_until:720,post:{url:'https://signed-secret.invalid',fields:{policy:'PRIVATE_SIGNED_POLICY'}}};},xhrFactory:()=>({upload:{},open(){},send(){sends++;queueMicrotask(()=>{this.status=201;this.onload();});}})};
 const input={environment:'env-owned',file:new File(['hello'],'test.txt'),key:'test.txt',contentType:'text/plain'};
 await assert.rejects(createUploader(options)(input));
 assert.ok(!storage.getItem('cloudhub.pending_uploads').includes('PRIVATE_SIGNED_POLICY'));assert.ok(!storage.getItem('cloudhub.pending_uploads').includes('signed-secret'));
 assert.equal((await createUploader(options)(input)).operation_id,'op-original');assert.equal(sends,1);
 const complete=calls.filter(x=>x.path.endsWith('/complete'));assert.equal(complete[0].key,complete[1].key);
});
for (const incompleteCode of ['UPLOAD_INCOMPLETE','UPLOAD_NOT_VISIBLE']) test('reload unfinished transfer reuses key: '+incompleteCode,async()=>{
 const storage=session(),calls=[];let sends=0,completed=0,keys=0;
 const options={storage,now:()=>1000,keyFor:()=>String(++keys),post:async(path,body,key)=>{calls.push({path,key});if(path.endsWith('/complete')){if(++completed===1)throw Object.assign(Error('not uploaded'),{code:incompleteCode});return {operation_id:'op-committed'};}return {upload_id:'upload-one',expires_at:120,complete_until:720,post:{url:'https://test.invalid',fields:{}}};},xhrFactory:()=>({upload:{},open(){},send(){queueMicrotask(()=>{if(++sends===1)this.onerror();else{this.status=201;this.onload();}});}})};
 const input={environment:'env-owned',file:new File(['hello'],'test.txt'),key:'test.txt',contentType:'text/plain'};
 await assert.rejects(createUploader(options)(input));await createUploader(options)(input);
 const init=calls.filter(x=>x.path.endsWith('/uploads'));assert.equal(init.length,2);assert.equal(init[0].key,init[1].key);
});
test('owned backend pending metadata permits cancellation without local storage',async()=>{
 let path;const upload=createUploader({storage:null,keyFor:s=>s,post:async p=>{path=p;return {status:'CANCELLED'};}});
 assert.equal((await upload.cancel('env-owned','upload-owned')).status,'CANCELLED');assert.equal(path,'/environments/env-owned/uploads/upload-owned/cancel');
});

test('website upload names the offending file and path before requesting a grant',async()=>{
 let calls=0;const upload=createUploader({post:async()=>{calls++;},keyFor:s=>s});
 await assert.rejects(upload({environment:'env-owned',file:new File(['<script src="/app.js?token=hidden"></script>'],'index.html'),key:'pages/index.html',contentType:'text/html',releaseId:'release-owned'}),error=>error.code==='RELEASE_UNVERSIONED_REFERENCE'&&error.file==='pages/index.html'&&error.asset_path==='/app.js'&&!error.message.includes('hidden'));
 assert.equal(calls,0);
});

test('direct upload retries completion with the same capability and key; no second file transfer',async()=>{
 const calls=[];let sends=0,completes=0;
 const upload=createUploader({now:()=>1000,keyFor:s=>'stable-'+s,post:async(path,body,key)=>{
  calls.push({path,body,key});if(path.endsWith('/complete')){if(++completes===1)throw Object.assign(Error('lost reply'),{status:503});return {operation_id:'op-existing'};}
  return {upload_id:'upload-local',expires_at:120,post:{url:'https://staging.invalid',fields:{key:'isolated'}}};
 },xhrFactory:()=>({upload:{},open(){},send(){sends++;queueMicrotask(()=>{this.status=201;this.onload();});}})});
 const file=new File([new Uint8Array(64000)],'real-file.pdf');const input={environment:'env-owned',file,key:'real-file.pdf',contentType:'application/pdf'};
 await assert.rejects(upload(input));const result=await upload(input);
 assert.equal(result.operation_id,'op-existing');assert.equal(sends,1);
 assert.equal(calls.filter(x=>x.path.endsWith('/uploads')).length,1);
 const retries=calls.filter(x=>x.path.endsWith('/complete'));assert.deepEqual(retries[0],retries[1]);
 assert.equal(calls[0].body.size,64000);assert.equal(calls[0].body.sha256.length,64);assert.equal(calls[0].body.content_base64,undefined);
});

test('continuous request has a null period, with a finite estimate horizon',()=>{
 const request=creationRequest({template_id:'T07'},{mode:'CONTINUOUS',estimateHours:'4',periodMinutes:'60',endingPolicy:'BACKUP_RETIRE',region:'us-east-1'});
 assert.equal(request.estimate_hours,4);assert.equal(request.operating_policy.period_minutes,null);assert.equal(request.operating_policy.mode,'CONTINUOUS');
});

test('server quote rejection keeps form and requires a new explicit review',async()=>{
 let sequence=0;const sent=[];
 const flow=createCreationFlow({now:()=>1000,keyFor:s=>s,costAllowed:()=>true,
  estimate:async body=>({approved:true,...body,quote_id:'quote-'+(++sequence),quote_expires_at:120,total_milliusd:200,first_period:{},renewal_period:{},after_shutdown:{},preview:{}}),
  create:async body=>{sent.push(body);throw Object.assign(Error('changed'),{status:409,code:'QUOTE_CHANGED'});}});
 flow.open({template_id:'T01',create_enabled:true});flow.change({estimateHours:'4'});
 await flow.next();await flow.next();await flow.next();flow.consent(true);await flow.submit();
 assert.equal(sent[0].quote_id,'quote-1');assert.equal(flow.snapshot().form.estimateHours,'4');assert.equal(flow.snapshot().consent,false);assert.equal(flow.snapshot().step,2);
 await flow.loadQuote();assert.equal(flow.snapshot().quote.quote_id,'quote-2');assert.equal(flow.snapshot().consent,false);
});
