import {setLanguage} from '../frontend/i18n.js';
await setLanguage('vi',{persist:false});
// Actual Gemini component + GPT callbacks. DOM fixtures, no browser/AWS claims.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {parseHTML} from 'linkedom';
import {createCreationView} from '../frontend/create-view.js';
function setup(callbacks={}){
  const {window}=parseHTML('<html><body><dialog id="create-dialog"></dialog></body></html>');globalThis.document=window.document;
  Object.defineProperty(window.HTMLSelectElement.prototype,'value',{configurable:true,get(){return this._testValue??this.querySelector('option')?.value??'';},set(value){this._testValue=String(value);}});
  const view=createCreationView(callbacks),$=s=>document.querySelector(s),event=name=>new window.Event(name,{bubbles:true,cancelable:true});
  const props={open:true,step:0,title:'Tạo Máy Linux',template:{template_id:'T01',name:'Máy Linux',operating_capabilities:{ending_policies:['PAUSE','BACKUP_RETIRE']}},description:'Linux nhỏ',backupScope:'/data, không gồm root',form:{estimateHours:'8',mode:'AUTO_OFF',periodMinutes:'5',endingPolicy:'BACKUP_RETIRE',budgetUsd:'10'},errors:{},supportsPause:true,quoteStatus:'idle',quote:null,quoteRows:[],unknown:[],busy:false,uncertain:false,consent:false,canNext:true,canSubmit:false,canCancel:true};
  view.update(props);return {view,$,props,event};
}

test('reviewed application labels are present and translate without losing entered content',async()=>{
  const {view,$,props}=setup();
  const app={...props,template:{...props.template,template_id:'T03',application_options:{'ap-southeast-1':[{release_id:'content-site-1',enabled:true,configuration_ids:['standard']}]}},form:{...props.form,region:'ap-southeast-1',configurationId:'standard',appRelease:'content-site-1',appTitle:'My project',appSubtitle:'My data'}};
  view.update({...app,step:3});assert.ok($('#review-summary').textContent.includes('content-site-1'));assert.ok($('#review-summary').textContent.includes('My project'));assert.ok($('#review-summary').textContent.includes('My data'));
  view.update(app);const label=$('label[for="application-title"]');assert.ok(label.textContent.trim());
  assert.ok($('label[for="application-release"]').textContent.trim());assert.ok($('label[for="application-subtitle"]').textContent.trim());
  const old=label.textContent;await setLanguage('en',{persist:false});
  try{view.update(app);assert.notEqual(label.textContent,old);assert.equal($('#application-title').value,'My project');assert.equal($('#application-release').value,'content-site-1');assert.equal($('#application-title').disabled,false);}
  finally{await setLanguage('vi',{persist:false});}
});
test('presentation emits string patches and navigation callbacks without API calls',()=>{
  const patches=[],next=[],back=[];const {view,$,props,event}=setup({onFieldChange:p=>patches.push(p),onNext:()=>next.push(1),onBack:()=>back.push(1)});
  $('#hours').value='4';$('#hours').dispatchEvent(event('change'));$('#create-next').click();view.update({...props,step:1});$('#operating-budget').value='1.234';$('#operating-budget').dispatchEvent(event('input'));$('#create-back').click();assert.deepEqual(patches,[{estimateHours:'4'},{budgetUsd:'1.234'}]);assert.equal(next.length,1);assert.equal(back.length,1);assert.equal($('#hours').closest('fieldset').id,'step-fieldset-0');
});

test('duration shortcuts only change the existing form field and respect continuous and locked requests',()=>{
 const patches=[];const {view,$,props}=setup({onFieldChange:p=>patches.push(p)});view.update({...props,step:1});
 $('#period-shortcuts [data-minutes="60"]').click();assert.deepEqual(patches,[{periodMinutes:'60'}]);
 view.update({...props,step:1,form:{...props.form,periodMinutes:'60'}});assert.equal($('#period-shortcuts [data-minutes="60"]').getAttribute('aria-pressed'),'true');
 for(const locked of [{form:{...props.form,mode:'CONTINUOUS'}},{busy:true},{uncertain:true}]){view.update({...props,step:1,...locked});assert.equal($('#period-shortcuts button').disabled,true);}
});
test('loading quote clears old prices and quote error wires the retry callback',()=>{
  let retries=0;const {view,$,props}=setup({onRetryQuote:()=>retries++});view.update({...props,step:2,quoteStatus:'ready',quoteRows:[{label:'Kỳ đầu',value:'0.454 USD'}]});assert.match($('#quote').textContent,/0.454 USD/);view.update({...props,step:2,quoteStatus:'loading'});assert.doesNotMatch($('#quote').textContent,/0.454 USD/);assert.match($('#quote').textContent,/Đang/);view.update({...props,step:2,quoteStatus:'error'});$('#create-retry-quote').click();assert.equal(retries,1);
});
test('uncertain result permits resending same request; busy blocks submit and cancel',()=>{
  let submissions=0;const {view,$,props,event}=setup({onSubmit:()=>submissions++});view.update({...props,step:3,uncertain:true,consent:true,canSubmit:true,canCancel:false});assert.equal($('#confirm').disabled,false);assert.match($('#confirm').textContent,/Thử gửi lại/);assert.equal($('#cancel').disabled,true);$('#create-form').dispatchEvent(event('submit'));assert.equal(submissions,1);view.update({...props,step:3,busy:true,canSubmit:false,canCancel:false});$('#create-form').dispatchEvent(event('submit'));assert.equal(submissions,1);assert.equal($('#confirm').disabled,true);
});

test('reloaded uncertain request permits explicit consent while configuration and navigation stay frozen',()=>{
  const choices=[];const {view,$,props,event}=setup({onConsent:value=>choices.push(value)});
  view.update({...props,step:3,uncertain:true,consent:false,canSubmit:false,canCancel:false});
  assert.equal($('#step-fieldset-3').disabled,false);assert.equal($('#confirm-cost').disabled,false);
  assert.equal($('#step-fieldset-0').disabled,true);assert.equal($('#confirm').disabled,true);assert.equal($('#cancel').disabled,true);
  $('#confirm-cost').checked=true;$('#confirm-cost').dispatchEvent(event('change'));assert.deepEqual(choices,[true]);
});
test('pause does not promise backup or destroyed EC2; unsupported option cannot be chosen',()=>{
  const {view,$,props}=setup();view.update({...props,step:3,form:{...props.form,endingPolicy:'PAUSE'}});assert.match($('#review-summary').textContent,/giữ nguyên instance|giữ máy chủ/);assert.match($('#review-summary').textContent,/không tự tạo backup 7 ngày/);view.update({...props,supportsPause:false,template:{template_id:'T02',name:'Website tĩnh'}});const pause=$('#ending-policy option[value=PAUSE]');assert.equal(pause.disabled,true);assert.equal(pause.hidden,true);
});
test('budget errors have accessible labels; user text escaped; input node preserved across updates',()=>{
  const {view,$,props}=setup();const input=$('#operating-budget');view.update({...props,step:1,title:'<img src=x onerror=alert(1)>',form:{...props.form,mode:'AUTO_RENEW',budgetUsd:''},errors:{budgetUsd:'Nhập số tiền hợp lệ'}});assert.equal($('#operating-budget'),input);assert.equal(input.getAttribute('aria-invalid'),'true');assert.equal(input.getAttribute('aria-describedby'),'operating-budget-error');assert.equal(document.querySelectorAll('img').length,0);assert.doesNotMatch($('#template-meta').textContent,/\[object Object\]/);assert.equal(input.value,'');
});
test('inactive fieldsets disabled and actual money disclaimer shown before consent',()=>{
  const {view,$,props}=setup();view.update({...props,step:2,quoteStatus:'ready',quoteRows:[{label:'Kỳ đầu',value:'0.454 USD'}]});assert.equal($('#step-fieldset-0').disabled,true);assert.equal($('#step-fieldset-3').disabled,true);assert.equal($('#step-fieldset-2').disabled,false);assert.match($('#quote').textContent,/không bảo đảm hóa đơn/i);
});
test('configuration choices emit state changes, display selected label and lock restored sizes',()=>{
  let patches=[];const {view,$,props,event}=setup({onFieldChange:p=>patches.push(p)});
  const template={...props.template,configuration_options:[{id:'standard',label:'8 GiB',description:'Dữ liệu 8 GiB',configuration:{data_gib:8},create_enabled:true},{id:'expanded',label:'16 GiB',description:'Dữ liệu 16 GiB',configuration:{data_gib:16},create_enabled:true}]};
  view.update({...props,template});$('#configuration-variant').value='expanded';$('#configuration-variant').dispatchEvent(event('change'));assert.deepEqual(patches,[{configurationId:'expanded'}]);
  view.update({...props,template,step:3,form:{...props.form,configurationId:'expanded'}});assert.match($('#review-summary').textContent,/16 GiB/);
  view.update({...props,template,configurationLocked:true,form:{...props.form,configurationId:'expanded'}});assert.equal($('#configuration-variant').disabled,true);assert.match($('#configuration-hint').textContent,/Khôi phục giữ đúng/);
});
