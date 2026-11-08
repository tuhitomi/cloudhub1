import {setLanguage} from '../frontend/i18n.js';
await setLanguage('vi',{persist:false});
// LOCAL DOM mocks, never an AWS infrastructure verification.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {parseHTML} from 'linkedom';
import {createLifecycleUI,operatingPolicy} from '../frontend/lifecycle.js';
const html=await readFile(new URL('../frontend/index.html',import.meta.url),'utf8');
function setup(template='T05',review=null){
  const {window}=parseHTML(html);globalThis.document=window.document;
  for(const select of document.querySelectorAll('select'))Object.defineProperty(select,'value',{writable:true,value:select.querySelector('option')?.value||''});
  for(const dialog of document.querySelectorAll('dialog')){dialog.showModal=()=>dialog.setAttribute('open','');dialog.close=()=>dialog.removeAttribute('open');}
  const $=s=>document.querySelector(s),calls=[],changes=[],tracked=[];
  const env={environment_id:'env-owned',template_id:template,status:'READY',deadline:5000,lifecycle_revision:3,
    operating_policy:{mode:'AUTO_OFF',period_minutes:5,ending_policy:template==='T05'?'PAUSE':'BACKUP_RETIRE',budget_limit_milliusd:null,confirmed:true},estimated_committed_milliusd:200,first_period_estimate:{total_milliusd:100}};
  const api=async(path,options)=>{calls.push({path,body:options?.body?JSON.parse(options.body):undefined});if(path.endsWith('/management-estimate'))return review||{approved:true,additional_commitment_milliusd:10,cumulative_after_milliusd:210,after_shutdown:{total_milliusd:2,period_hours:24},unknown:[]};if(path.endsWith('/renewals'))return {items:[],total_count:0,truncated:false};return env;};
  const mutate=async(path,body)=>{changes.push({path,body});return {operation_id:'op-accepted',status:'QUEUED'};};
  const element=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
  const ui=createLifecycleUI({api,mutate,track:op=>tracked.push(op),refresh:async()=>{},element,timestamp:value=>String(value),notice:text=>$('#notice').textContent=text});
  return {$,ui,env,calls,changes,tracked};
}
test('renewal rejection localizes its reason while preserving the diagnostic code',async()=>{
  await setLanguage('en',{persist:false});
  try{
    const {$,ui,env}=setup();env.renewal_blocked_reason={code:'QUOTA_EXCEEDED',message:'Không đủ hạn mức để gia hạn.'};
    await ui.detail(env);const text=$('#environment-detail').textContent;
    assert.ok(text.includes('QUOTA_EXCEEDED'));assert.ok(!text.includes('Không đủ hạn mức'));
  }finally{await setLanguage('vi',{persist:false});}
});

test('readiness proof is independent from the current management job',async()=>{
  const {$,ui,env}=setup();env.detail={current_operation:{operation_id:'op-backup',action:'backup',phase:'BACKUP'},readiness:{operation_id:'op-restored',infrastructure_ready_at:4100,data_verified_at:4200}};
  await ui.detail(env);const text=$('#environment-detail').textContent;
  assert.ok(text.includes('op-backup'));assert.ok(text.includes('4100'));assert.ok(text.includes('4200'));
  env.detail.readiness.data_verified_at=null;await ui.detail(env);
  assert.ok(!$('#environment-detail').textContent.includes('4200'));
});

test('latest backup uses localized status and invalidates obsolete retention after deletion',async()=>{
  const {$,ui,env}=setup();env.detail={latest_backup:{recovery_point:'rp-old',status:'DELETED',created_at:1000,retain_until:99999}};
  await ui.detail(env);const text=$('#environment-detail').textContent;
  assert.ok(text.includes('rp-old'));assert.ok(!text.includes('DELETED'));assert.ok(!text.includes('99999'));
  assert.ok(text.includes('hạn lưu cũ không còn hiệu lực'));
});
test('forecast horizon and operating period are separate; auto renewal is off by default',()=>{
  const {$,ui}=setup();ui.configureCreate({template_id:'T05'});$('#hours').value='8';$('#operating-period').value='15';
  const request=ui.createRequest();assert.equal(request.estimate_hours,8);assert.equal(request.operating_policy.period_minutes,15);assert.equal(request.operating_policy.mode,'AUTO_OFF');assert.equal(request.operating_policy.budget_limit_milliusd,null);assert.equal($('#operating-budget-field').hidden,true);
});
test('enabling auto renewal requires a visible user-selected cumulative budget',()=>{
  const {$,ui}=setup();ui.configureCreate({template_id:'T05'});$('#operating-mode').value='AUTO_RENEW';$('#operating-budget').value='2.345';ui.toggleCreate();
  assert.equal($('#operating-budget-field').hidden,false);assert.equal($('#operating-budget').required,true);assert.equal(ui.createRequest().operating_policy.budget_limit_milliusd,2345);
});
test('unsupported templates never offer pause and explain the supported policy',()=>{
  const {$,ui}=setup('T04');ui.configureCreate({template_id:'T04'});assert.equal($('#ending-policy').querySelectorAll('option').length,1);assert.equal($('#ending-policy').querySelector('option').value,'BACKUP_RETIRE');assert.match($('#pause-support').textContent,/không hỗ trợ tạm dừng/);
});
test('management renewal waits for cost consent then sends only period/confirmation/revision',async()=>{
  const {$,ui,env,changes,tracked}=setup();await ui.openManagement(env,'renew');
  await $('#management-form').onsubmit({preventDefault(){}});assert.equal(changes.length,0);
  $('#management-confirmed').checked=true;await $('#management-form').onsubmit({preventDefault(){}});
  assert.deepEqual(changes[0].body,{confirmed:true,expected_revision:3,minutes:5,quote_id:undefined});assert.equal(changes[0].path,'/environments/env-owned/renew');assert.equal(tracked[0].operation_id,'op-accepted');assert.equal($('#management-dialog').hasAttribute('open'),false);
});
test('pause/end confirmation explains preserved data and ongoing charges before submitting',async()=>{
  const {$,ui,env,changes}=setup();await ui.openManagement(env,'end');assert.match($('#management-description').textContent,/Tạm dừng/);assert.match($('#management-description').textContent,/phí lưu dữ liệu/);assert.equal(changes.length,0);
});
test('environment details distinguish paused infrastructure from retirement and expose sync/history',async()=>{
  const {$,ui,env}=setup();env.status='PAUSED';env.schedule_pending=true;env.pause_report={deleted:[],retained:[{id:'vol-kept'}],residual:[],unknown:[],billable:[{id:'vol-kept'}]};
  await ui.detail(env);const text=$('#environment-detail').textContent;assert.match(text,/Đã tạm dừng; chưa có lịch/);assert.match(text,/cần đồng bộ/);assert.match(text,/vol-kept/);assert.match(text,/Chưa có lần gia hạn/);
});
test('legacy environment display always defaults to automatic backup-retirement, never renewal',()=>{
  assert.equal(operatingPolicy({duration_hours:2}).mode,'AUTO_OFF');assert.equal(operatingPolicy({duration_hours:2}).ending_policy,'BACKUP_RETIRE');assert.equal(operatingPolicy({duration_hours:2}).period_minutes,120);
});
test('editing management period immediately invalidates prior consent before blur',async()=>{
  const {$,ui,env,changes}=setup();await ui.openManagement(env,'renew');$('#management-confirmed').checked=true;$('#management-minutes').value='15';$('#management-minutes').dispatchEvent(new document.defaultView.Event('input'));
  assert.equal($('#management-confirmed').checked,false);assert.equal($('#management-submit').disabled,true);await $('#management-form').onsubmit({preventDefault(){}});assert.equal(changes.length,0);
});
test('cancelled management cannot reuse earlier quote consent',async()=>{
  const {$,ui,env,changes}=setup();await ui.openManagement(env,'renew');$('#management-confirmed').checked=true;$('#management-close').onclick();await $('#management-form').onsubmit({preventDefault(){}});assert.equal($('#management-dialog').hasAttribute('open'),false);assert.equal($('#management-submit').disabled,true);assert.equal($('#management-confirmed').checked,false);assert.equal(changes.length,0);
});

test('management confirmation is visibly disabled until cost consent and disabled again on uncheck',async()=>{
  const {$,ui,env}=setup();await ui.openManagement(env,'end');assert.equal($('#management-submit').disabled,true);
  $('#management-confirmed').checked=true;$('#management-confirmed').dispatchEvent(new document.defaultView.Event('change'));assert.equal($('#management-submit').disabled,false);
  $('#management-confirmed').checked=false;$('#management-confirmed').dispatchEvent(new document.defaultView.Event('change'));assert.equal($('#management-submit').disabled,true);
});

test('editing back to the original value without a native change event still offers quote recovery',async()=>{
  const {$,ui,env,calls}=setup();await ui.openManagement(env,'renew');const input=$('#management-minutes');input.value='5';input.dispatchEvent(new document.defaultView.Event('input'));
  assert.equal($('#management-submit').disabled,true);assert.ok($('#management-retry-quote'));await $('#management-retry-quote').onclick();assert.equal(calls.filter(call=>call.path.endsWith('/management-estimate')).length,2);
  $('#management-confirmed').checked=true;$('#management-confirmed').dispatchEvent(new document.defaultView.Event('change'));assert.equal($('#management-submit').disabled,false);
});


test('termination data consent remains explicit and sends revision even without priced costs',async()=>{
  const review={approved:true,quote_id:'quote-data-consent',review_kind:'TERMINATION_DATA_CONSENT',additional_commitment_milliusd:null,cumulative_after_milliusd:null,after_shutdown:{total_milliusd:null,period_hours:168},unknown:[]};
  const {$,ui,env,changes}=setup('T07',review);await ui.openManagement(env,'destroy');
  assert.equal($('#management-submit').disabled,true);assert.match($('#management-quote').textContent,/7 ngày/);
  assert.match($('#management-quote').textContent,/chưa định giá/);assert.equal(changes.length,0);
  $('#management-confirmed').checked=true;await $('#management-form').onsubmit({preventDefault(){}});
  assert.deepEqual(changes[0].body,{confirmed:true,expected_revision:3,quote_id:'quote-data-consent'});
});


test('compatible frontend keeps the legacy destroy contract before backend rollout',async()=>{
  const {$,ui,env,changes}=setup('T07');await ui.openManagement(env,'destroy');
  $('#management-confirmed').checked=true;await $('#management-form').onsubmit({preventDefault(){}});
  assert.deepEqual(JSON.parse(JSON.stringify(changes[0].body)),{});
});
