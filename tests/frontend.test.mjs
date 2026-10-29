import {setLanguage} from '../frontend/i18n.js';
await setLanguage('vi',{persist:false});
// DOM unit tests with mocked services. This is not browser or AWS evidence.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {parseHTML} from 'linkedom';
const html=await readFile(new URL('../frontend/index.html',import.meta.url),'utf8');
const source=await readFile(new URL('../frontend/portal.js',import.meta.url),'utf8');
const {createPortal}=await import('../frontend/portal.js');
const quota={active:1,max_active:2,remaining_environments:1,user_budget_milliusd:10000,remaining_milliusd:2000};
const token=groups=>'header.'+Buffer.from(JSON.stringify({'cognito:groups':groups,exp:Math.floor(Date.now()/1000)+3600,sub:'alice',iss:'https://cognito-idp.ap-southeast-1.amazonaws.com/pool',client_id:'client',token_use:'access'})).toString('base64url')+'.signature';
const flush=async()=>{for(let i=0;i<8;i++)await new Promise(resolve=>setImmediate(resolve));};
function setup(groups=[]){
  const {window}=parseHTML(html);globalThis.document=window.document;globalThis.window=window;
  Object.defineProperty(window.HTMLSelectElement.prototype,'value',{configurable:true,get(){return this._testValue??this.querySelector('option[selected]')?.value??this.querySelector('option')?.value??'';},set(value){this._testValue=String(value);}});
  for(const select of document.querySelectorAll('select'))Object.defineProperty(select,'value',{writable:true,value:select.querySelector('option')?.getAttribute('value')||''});
  for(const dialog of document.querySelectorAll('dialog')){Object.defineProperty(dialog,'open',{get(){return dialog.hasAttribute('open');}});dialog.showModal=()=>dialog.setAttribute('open','');dialog.close=()=>dialog.removeAttribute('open');}
  for(const form of document.querySelectorAll('form'))form.reset=()=>{for(const field of form.querySelectorAll('input')){field.value='';field.checked=false;}};
  const responses=new Map([['/admin/announcements',{items:[],publication_enabled:true}],['/limits',quota],['/notifications',{items:[]}],['/operations',{items:[]}],['/admin/environments',{items:[]}],['/admin/users',{items:[],next_cursor:null}],['/admin/notifications',{status:'NOT_CONFIGURED',email:''}],['/admin/signup-defaults',{max_active:2,budget_milliusd:10000}]]),calls=[];
  const element=(tag,text,cls)=>{const value=document.createElement(tag);if(text!==undefined)value.textContent=text;if(cls)value.className=cls;return value;};
  const button=(text,fn,disabled=false)=>{const value=element('button',text);value.disabled=disabled;value.addEventListener('click',()=>Promise.resolve(fn()).catch(error=>document.querySelector('#notice').textContent=error.message));return value;};
  const api=async path=>{calls.push(path);const resource=path.split('?')[0];if(!responses.has(resource))throw Error('Unexpected endpoint '+path);return responses.get(resource);};
  const context={api,post:api,notice:text=>document.querySelector('#notice').textContent=text,element,button,timestamp:n=>String(n||''),track:()=>{},refresh:async()=>{},operations:new Map(),renderOperations:()=>{},cfg:{configured:true,region:'ap-southeast-1',clientId:'client'},getToken:()=>token(groups),ensureToken:async()=>{},mutate:api};
  return {portal:createPortal(context),context,responses,calls,element,$:selector=>document.querySelector(selector)};
}
test('creation fails closed until limits load and enforces remaining reservation',async()=>{
  const {portal,responses}=setup();assert.equal(portal.costAllowed({approved:true,total_milliusd:100}),false);
  await portal.loadLimits();assert.equal(portal.costAllowed({approved:true,total_milliusd:1999}),true);assert.equal(portal.costAllowed({approved:true,total_milliusd:2001}),false);
  responses.set('/limits',{...quota,remaining_environments:0});await portal.loadLimits();assert.equal(portal.costAllowed({approved:true,total_milliusd:0}),false);
});
test('history shares search, state and template filters and renders IDs as text',()=>{
  const {portal,$}=setup();const env={environment_id:'env-<img src=x>',template_id:'T01',status:'DELETED',retired_at:100};
  portal.renderHistory([env,{...env,environment_id:'env-active',status:'READY'}]);assert.equal($('#environment-history').querySelectorAll('article').length,1);assert.equal($('#environment-history').querySelectorAll('img').length,0);
  $('#environment-search').value='active';portal.renderHistory([env]);assert.equal($('#environment-history').querySelectorAll('article').length,0);
  $('#environment-search').value='';$('#environment-template').value='T02';assert.equal(portal.filter([env]).length,0);
});
test('a recovery point in use disables download and delete, with honest native labels',()=>{
  const {portal,element}=setup();const card=element('article');portal.backupExtras(card,{recovery_point:'rp-id',template_id:'T01',status:'AVAILABLE',in_use:true,retain_until:Date.now()/1000+3600});
  assert.equal(card.querySelector('button').textContent,'Tải thông tin snapshot');assert.ok([...card.querySelectorAll('button')].every(value=>value.disabled));
});
test('a final retirement backup blocks deletion while still allowing download',()=>{
  const {portal,element}=setup();const card=element('article');portal.backupExtras(card,{recovery_point:'rp-id',template_id:'T01',status:'AVAILABLE',retirement_protected:true,retain_until:Date.now()/1000+3600});
  const buttons=card.querySelectorAll('button');assert.equal(buttons[0].disabled,false);assert.equal(buttons[1].disabled,true);assert.match(card.textContent,/được bảo vệ/);
});

test('failed provisioning cannot retry; cancelling and native export have separate controls',()=>{
  const {portal,element}=setup();const card=element('article');portal.operationExtras(card,{operation_id:'op-id',status:'FAILED',phase:'CREATE'});
  const buttons=card.querySelectorAll('button');assert.equal(buttons[0].disabled,true);assert.equal(buttons[1].textContent,'Đóng tác vụ lỗi');
});
test('owned EFS retry waits for backend eligibility',async()=>{
  const {portal,element,responses}=setup();portal.renderHistory([{environment_id:'env-efs',template_id:'T08',status:'CREATE_FAILED'}]);
  for(const [action,disabled] of [['create',false],['restore',true]]){
    responses.set('/operations/op-efs/actions',{retry:{allowed:!disabled},cancel:{allowed:true}});
    const card=element('article');portal.operationExtras(card,{operation_id:'op-efs',environment_id:'env-efs',action,status:'FAILED',failed_phase:'WAIT_CREATE'});
    assert.equal(card.querySelector('button').disabled,true);await flush();assert.equal(card.querySelector('button').disabled,disabled);
  }
});
test('admin visibility uses exact group and pending SNS confirmation keeps test disabled',async()=>{
  const bad=setup('notadmin');assert.equal(bad.portal.isAdmin(),false);
  const {portal,responses,$}=setup(['admin']);responses.set('/admin/notifications',{status:'PENDING_CONFIRMATION',email:'admin@example.com'});
  await portal.refreshOwn();await portal.loadAdmin();assert.equal($('#admin').hidden,false);assert.equal($('#sns-test').disabled,true);assert.match($('#sns-status').textContent,/Confirm subscription/);
});
test('password change uses Cognito directly and clears passwords on provider error',async()=>{
  const {context,$}=setup();const requests=[];globalThis.fetch=async(url,options)=>{requests.push({url,...options});return {ok:false,json:async()=>({__type:'NotAuthorizedException'})};};
  $('#previous-password').value='old-secret';$('#new-password').value='new-secret';$('#change-password-form').onsubmit({preventDefault(){},currentTarget:$('#change-password-form')});await flush();
  assert.equal(requests.length,1);assert.equal(requests[0].url,'https://cognito-idp.ap-southeast-1.amazonaws.com/');assert.match(requests[0].headers['X-Amz-Target'],/ChangePassword$/);
  assert.equal($('#previous-password').value,'');assert.equal($('#new-password').value,'');assert.match($('#account-notice').textContent,/không hợp lệ/);assert.equal(context.operations.size,0);
});
test('forgot/reset uses confirmation code and clears new password after success',async()=>{
  const {$}=setup();const requests=[];globalThis.fetch=async(url,options)=>{requests.push(JSON.parse(options.body));return {ok:true,json:async()=>({})};};
  $('#forgot-email').value='student@example.com';$('#reset-code').value='123456';$('#reset-password').value='NewPassword123!';$('#reset-form').onsubmit({preventDefault(){},currentTarget:$('#reset-form')});await flush();
  assert.equal(requests[0].ConfirmationCode,'123456');assert.equal(requests[0].Username,'student@example.com');assert.equal($('#reset-password').value,'');assert.match($('#password-notice').textContent,/Đã đặt mật khẩu/);
});

test('password recovery remains reachable from sign-in after compacting the header',()=>{
 const {$}=setup();$('#login-dialog').showModal();assert.equal($('#forgot-password').closest('form').id,'login-form');assert.equal($('#forgot-password').type,'button');
 $('#forgot-password').click();assert.equal($('#password-dialog').open,true);assert.equal($('#forgot-form').hidden,false);$('#password-close').click();assert.equal($('#password-dialog').open,false);assert.equal($('#login-dialog').open,true);
});

for(const [code,expected] of [['CodeMismatchException',/không đúng/],['ExpiredCodeException',/hết hạn/]]){
  test('password reset '+code+' retains reset screen and clears the rejected password',async()=>{
    const {$}=setup();$('#forgot-email').value='student@example.com';$('#reset-form').hidden=false;$('#reset-code').value='000000';$('#reset-password').value='OnlyLocalTest123!';
    globalThis.fetch=async()=>({ok:false,json:async()=>({__type:code})});
    $('#reset-form').onsubmit({preventDefault(){},currentTarget:$('#reset-form')});await flush();
    assert.match($('#password-notice').textContent,expected);assert.equal($('#reset-password').value,'');assert.equal($('#reset-form').hidden,false);
  });
}
test('complete app starts with real HTML and mocked owned API, with no browser automation',async()=>{
  const {context,$}=setup();window.CLOUDHUB=context.cfg;const storage=new Map([['cloudhub_access_token',token([])]]);globalThis.sessionStorage={getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key),clear:()=>storage.clear()};
  globalThis.location={search:'',pathname:'/',hash:'',assign(){}};globalThis.history={replaceState(){}};
  const values={'/account':{email_verified:true,role:'user'},'/templates':{items:[]},'/environments':{items:[]},'/recovery-points':{items:[]},'/limits':quota,'/notifications':{items:[]},'/operations':{items:[]}};
  globalThis.fetch=async url=>{const path=new URL(url,'https://api.example').pathname;if(path==='/ui-context')return {ok:true,json:async()=>({country_code:'VN'})};if(path==='/account/preferences')return {ok:true,json:async()=>({language_preference:'vi'})};assert.ok(values[path],'unexpected '+path);return {ok:true,json:async()=>values[path]};};window.CLOUDHUB.apiBase='https://api.example';
  const timer=globalThis.setInterval;globalThis.setInterval=()=>1;
  try{await loadApp();await flush();assert.match($('#limits-summary').textContent,/Còn 1 môi trường/);assert.equal($('#logout').hidden,false);assert.equal($('#admin').hidden,true);assert.match($('#notice').textContent,/Đã đăng nhập/);assert.match($('#catalog').textContent,/Chưa có mẫu/);assert.match($('#backups').textContent,/Chưa có bản sao/);}finally{globalThis.setInterval=timer;}
});

async function loadApp(){
  const {disposeLanguageUI}=await import('../frontend/i18n.js');disposeLanguageUI();
  let app=await readFile(new URL('../frontend/app.js',import.meta.url),'utf8');
  app=app.replace(/(['"])\.\/([a-z0-9-]+\.js)\1/g,(_,quote,name)=>JSON.stringify(new URL('../frontend/'+name,import.meta.url).href));
  await import('data:text/javascript;base64,'+Buffer.from(app+'\n// test-run '+Math.random()).toString('base64'));
}

test('new frontend accepts the previous cached HTML shell without replacing existing inputs',async()=>{
 const {context,$}=setup();window.CLOUDHUB={...context.cfg,configured:false};globalThis.localStorage=undefined;
 globalThis.sessionStorage={getItem:()=>null,setItem(){},removeItem(){}};globalThis.location={search:'',pathname:'/',hash:'',assign(){}};globalThis.history={replaceState(){}};
 for(const id of ['file-dropzone','file-selection','record-result','ssh-dialog'])$('#'+id).remove();$('#files-title').removeAttribute('id');
 const original=$('#record-id');original.value='preserved-input';globalThis.fetch=async()=>({ok:true,json:async()=>({country_code:'VN'})});
 const timer=globalThis.setInterval;globalThis.setInterval=()=>1;
 try{await loadApp();await flush();for(const id of ['file-dropzone','file-selection','record-result','ssh-copy','ssh-close','files-title'])assert.ok($('#'+id),id);
  assert.equal($('#record-id'),original);assert.equal(original.value,'preserved-input');assert.equal($('#catalog').querySelectorAll('article').length,9);
 }finally{globalThis.setInterval=timer;}
});

test('SSH copy uses the backend command and never places private key material in the page',async()=>{
 const {context,$}=setup();window.CLOUDHUB={...context.cfg,apiBase:'https://api.example'};globalThis.localStorage=undefined;
 const storage=new Map([['cloudhub_access_token',token([])]]);globalThis.sessionStorage={getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)};
 globalThis.location={search:'',pathname:'/',hash:'',assign(){}};globalThis.history={replaceState(){}};
 const values={'/account':{email_verified:true,role:'user'},'/templates':{items:[]},'/environments':{items:[{environment_id:'env-owned',template_id:'T01',status:'READY'}]},'/recovery-points':{items:[]},'/limits':quota,'/notifications':{items:[]},'/operations':{items:[]}};
 const command='ssh -i env-owned.pem ubuntu@192.0.2.1 -p 2222';let copied='';
 globalThis.fetch=async(url)=>{const path=new URL(url,'https://api.example').pathname;
  if(path==='/ui-context')return {ok:true,json:async()=>({country_code:'VN'})};
  if(path==='/account/preferences')return {ok:true,json:async()=>({language_preference:'vi'})};
  if(path.endsWith('/ssh-key'))return {ok:true,json:async()=>({filename:'env-owned.pem',private_key:'SYNTHETIC_KEY_NOT_A_CREDENTIAL',command})};
  assert.ok(values[path],path);return {ok:true,json:async()=>structuredClone(values[path])};
 };
 const timer=globalThis.setInterval,previousNavigator=Object.getOwnPropertyDescriptor(globalThis,'navigator');globalThis.setInterval=()=>1;
 Object.defineProperty(globalThis,'navigator',{configurable:true,value:{clipboard:{writeText:async value=>{copied=value;}}}});
 try{await loadApp();await flush();const {t}=await import('../frontend/i18n.js');[...$('#environments').querySelectorAll('button')].find(b=>b.textContent===t('ui.7b014eaf12f3')).click();await flush();
  assert.equal($('#ssh-dialog').open,true);assert.equal($('#ssh-command').value,command);assert.doesNotMatch(document.body.textContent,/SYNTHETIC_KEY_NOT_A_CREDENTIAL/);$('#ssh-copy').click();await flush();assert.equal(copied,command);
 }finally{globalThis.setInterval=timer;if(previousNavigator)Object.defineProperty(globalThis,'navigator',previousNavigator);else delete globalThis.navigator;}
});

for(const offlineFirst of [false,true])test('new tab restores remembered login through refresh only; temporary offline='+offlineFirst,async()=>{
  const {context,$}=setup();window.CLOUDHUB={...context.cfg,apiBase:'https://api.example'};
  const memory=()=>{const map=new Map();return {getItem:k=>map.get(k)||null,setItem:(k,v)=>map.set(k,String(v)),removeItem:k=>map.delete(k)};};
  const persistent=memory();globalThis.localStorage=persistent;globalThis.sessionStorage=memory();
  const {createSession}=await import('../frontend/session.js');
  const previous=createSession({cfg:context.cfg,tab:memory(),persistent,eventTarget:null});previous.accept({access_token:token([]),refresh_token:'synthetic-refresh'});previous.dispose();
  globalThis.location={search:'',pathname:'/',hash:'',assign(){},reload(){}};globalThis.history={replaceState(){}};
  const values={'/account':{email_verified:true,role:'user'},'/templates':{items:[{template_id:'T07',services:['S3'],create_enabled:true}]},'/environments':{items:[]},'/recovery-points':{items:[]},'/limits':quota,'/notifications':{items:[]},'/operations':{items:[]}};let attempts=0,revocations=0;
  globalThis.fetch=async(url,options={})=>{
    if(String(url).includes('cognito-idp.')){
      const body=JSON.parse(options.body);if(options.headers['X-Amz-Target'].endsWith('.RevokeToken')){revocations++;assert.equal(body.Token,'synthetic-refresh');assert.equal(body.ClientId,'client');return {ok:true,json:async()=>({})};}assert.equal(body.AuthFlow,'REFRESH_TOKEN_AUTH');assert.equal(body.AuthParameters.PASSWORD,undefined);
      if(++attempts===1&&offlineFirst)throw new TypeError('synthetic offline');return {ok:true,json:async()=>({AuthenticationResult:{AccessToken:token([])}})};
    }
    const path=new URL(url,'https://api.example').pathname;
    if(path==='/ui-context')return {ok:true,json:async()=>({country_code:'VN'})};
    if(path==='/account/preferences')return {ok:true,json:async()=>({language_preference:'vi'})};
    assert.ok(values[path],'unexpected '+path);return {ok:true,json:async()=>values[path]};
  };
  const timer=globalThis.setInterval;globalThis.setInterval=()=>1;
  try{
    await loadApp();await flush();
    if(offlineFirst){assert.match($('#notice').textContent,/Kiểm tra kết nối/);$('#login-email').value='keep@example.com';$('#notice button').click();await flush();assert.equal($('#login-email').value,'keep@example.com');}
    assert.equal($('#logout').hidden,false);assert.equal($('#login-dialog').open,false);assert.equal($('#catalog .tag').textContent,'T07');assert.equal(attempts,offlineFirst?2:1);
    persistent.setItem('cloudhub.theme','dark');sessionStorage.setItem('upload-journal','keep');await $('#logout').onclick();await flush();
    assert.equal($('#logout').hidden,true);assert.equal($('#account-settings').hidden,true);assert.equal($('#catalog').querySelectorAll('article').length,9);
    assert.equal(revocations,1);assert.equal(persistent.getItem('cloudhub.auth.remember.v1'),null);assert.equal(persistent.getItem('cloudhub.theme'),'dark');assert.equal(sessionStorage.getItem('upload-journal'),'keep');
  }finally{globalThis.setInterval=timer;}
});

test('anonymous visitors see exactly T01–T09 and every selection opens login without protected requests',async()=>{
  const {context,$}=setup();window.CLOUDHUB={...context.cfg,apiBase:'https://api.example'};
  const storage=new Map();globalThis.sessionStorage={getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)};
  globalThis.localStorage={getItem:()=>null,setItem(){}};
  globalThis.location={search:'',pathname:'/',hash:'',assign(){}};globalThis.history={replaceState(){}};
  const requests=[];globalThis.fetch=async(url,options)=>{requests.push({url,options});if(url==='/ui-context')return {ok:true,json:async()=>({country_code:'VN'})};assert.equal(url,'https://api.example/public/catalog');return {ok:false,status:503,json:async()=>({})};};
  const timer=globalThis.setInterval;globalThis.setInterval=()=>1;
  try{
    await loadApp();await flush();
    assert.deepEqual([...$('#catalog').querySelectorAll('.tag')].map(e=>e.textContent),['T01','T02','T03','T04','T05','T06','T07','T08','T09']);
    assert.equal($('#catalog').querySelectorAll('.badge').length,0);assert.match($('#notice').textContent,/Xem trước 9 mẫu/);
    for(const button of $('#catalog').querySelectorAll('.catalog-select')){
      assert.equal(button.disabled,false);button.click();await flush();
      assert.equal($('#login-dialog').open,true);assert.equal($('#create-dialog').open,false);$('#login-close').click();
    }
    await setLanguage('en',{persist:false});await flush();
    assert.equal($('#catalog').querySelectorAll('article').length,9);assert.equal($('#catalog h3').textContent,'Linux machine');assert.match($('#notice').textContent,/Browse all 9 templates/);
    $('#catalog button').click();await flush();assert.equal($('#login-dialog').open,true);
    assert.deepEqual(requests.map(r=>r.url).sort(),['/ui-context','https://api.example/public/catalog']);assert.equal(requests[1].options.headers.Authorization,undefined);assert.equal(storage.size,0);
  }finally{globalThis.setInterval=timer;await setLanguage('vi',{persist:false});}
});

for(const fromGuestSelection of [false,true])test('login uses backend availability without auto-estimate or create; resume selected template='+fromGuestSelection,async()=>{
  const {context,$}=setup();window.CLOUDHUB={...context.cfg,apiBase:'https://api.example'};
  const storage=new Map();globalThis.sessionStorage={getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)};
  globalThis.localStorage={getItem:()=>null,setItem(){}};
  globalThis.location={search:'',pathname:'/',hash:'',assign(){}};globalThis.history={replaceState(){}};
  const jwt='header.'+Buffer.from(JSON.stringify({sub:'alice',iss:'https://cognito-idp.ap-southeast-1.amazonaws.com/pool',exp:Math.floor(Date.now()/1000)+3600,client_id:'client',token_use:'access'})).toString('base64url')+'.signature';
  const requests=[],values={'/account':{email_verified:true,role:'user'},'/templates':{items:[{template_id:'T07',services:['S3'],create_enabled:false},{template_id:'T01',services:['EC2'],create_enabled:true}]},'/environments':{items:[]},'/recovery-points':{items:[]},'/limits':quota,'/notifications':{items:[]},'/operations':{items:[]}};
  globalThis.fetch=async(url,options={})=>{
    requests.push({url,method:options.method||'GET'});
    if(String(url).includes('cognito-idp.'))return {ok:true,json:async()=>({AuthenticationResult:{AccessToken:jwt}})};
    const path=new URL(url,'https://api.example').pathname;
    if(path==='/ui-context')return {ok:true,json:async()=>({country_code:'VN'})};
    if(path==='/account/preferences')return {ok:true,json:async()=>({language_preference:'vi'})};
    assert.ok(values[path],'Unexpected endpoint '+path);assert.ok(options.headers.Authorization.startsWith('Bearer '));
    return {ok:true,json:async()=>values[path]};
  };
  const timer=globalThis.setInterval;globalThis.setInterval=()=>1;
  try{
    await loadApp();await flush();assert.equal($('#catalog').querySelectorAll('article').length,9);
    (fromGuestSelection?$('#catalog [data-template="T01"] .catalog-select'):$('#login')).click();await flush();$('#login-email').value='local@example.com';$('#login-password').value='LocalFixtureOnly123!';
    await $('#login-form').onsubmit({preventDefault(){}});await flush();
    assert.deepEqual([...$('#catalog').querySelectorAll('.tag')].map(e=>e.textContent),['T07','T01']);
    const buttons=$('#catalog').querySelectorAll('button');assert.equal(buttons[0].disabled,true);assert.equal(buttons[1].disabled,false);
    assert.equal($('#login-dialog').open,false);assert.equal($('#create-dialog').open,fromGuestSelection);assert.equal($('#logout').hidden,false);
    assert.equal(requests.filter(r=>r.method==='POST'&&!r.url.includes('cognito-idp.')).length,0);
    if(!fromGuestSelection){buttons[1].click();await flush();}assert.equal($('#create-dialog').open,true);
  }finally{globalThis.setInterval=timer;}
});

test('full app keeps API request/key after 503 uncertainty and tracks one accepted operation',async()=>{
  const {context,$}=setup();const storage=new Map([['cloudhub_access_token',token([])]]);globalThis.sessionStorage={getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key),clear:()=>storage.clear()};globalThis.location={search:'',pathname:'/',hash:'',assign(){}};globalThis.history={replaceState(){}};window.CLOUDHUB={...context.cfg,apiBase:'https://api.example'};
  const requests=[];const values={'/account':{email_verified:true,role:'user'},'/templates':{items:[{template_id:'T01',name:'Máy Linux',purpose:'Dùng Linux',services:['EC2'],create_enabled:true}]},'/environments':{items:[]},'/recovery-points':{items:[]},'/limits':quota,'/notifications':{items:[]},'/operations':{items:[]}};
  globalThis.fetch=async(url,options={})=>{const path=new URL(url,'https://api.example').pathname;if(path==='/ui-context')return {ok:true,json:async()=>({country_code:'VN'})};if(path==='/account/preferences')return {ok:true,json:async()=>({language_preference:'vi'})};if(path==='/estimates'){const request=JSON.parse(options.body);return {ok:true,json:async()=>({...request,approved:true,total_milliusd:454,first_period:{total_milliusd:350},renewal_period:{total_milliusd:200},after_shutdown:{total_milliusd:104,period_hours:168},preview:{total_milliusd:500},initial_commitment_milliusd:454})};}if(path==='/environments'&&options.method==='POST'){requests.push(options);return requests.length===1?{ok:false,status:503,json:async()=>({error:{message:'Mất phản hồi'}})}:{ok:true,status:202,json:async()=>({operation_id:'op-local-accepted',action:'create',status:'RUNNING',phase:'WAIT_CREATE'})};}assert.ok(values[path],'unexpected '+path);return {ok:true,json:async()=>values[path]};};
  const timer=globalThis.setInterval;globalThis.setInterval=()=>1;
  try{await loadApp();await flush();$('#catalog button').click();await flush();for(let i=0;i<3;i++){$('#create-next').click();await flush();}$('#confirm-cost').checked=true;$('#confirm-cost').dispatchEvent(new window.Event('change'));$('#create-form').dispatchEvent(new window.Event('submit',{cancelable:true}));await flush();assert.match($('#create-notice').textContent,/Mất phản hồi/);assert.equal($('#confirm').disabled,false);$('#create-form').dispatchEvent(new window.Event('submit',{cancelable:true}));await flush();assert.equal(requests.length,2);assert.equal(requests[0].body,requests[1].body);assert.equal(requests[0].headers['Idempotency-Key'],requests[1].headers['Idempotency-Key']);assert.ok(requests[0].headers.Authorization.startsWith('Bearer '));assert.equal(JSON.parse(requests[0].body).owner_id,undefined);assert.match($('#operations').textContent,/op-local-accepted/);assert.match($('#operations').textContent,/Chờ AWS tạo/);assert.equal($('#create-dialog').hasAttribute('open'),false);}finally{globalThis.setInterval=timer;}
});


test('continuous budget notices never announce automatic retirement',async()=>{
 const {portal,responses,$}=setup();responses.set('/notifications',{items:[{type:'CONTINUOUS_BUDGET_WARNING',environment_id:'env-continuous',created_at:1000,message_key:'continuous.budgetWarning'}]});
 await portal.refreshOwn();assert.match($('#notification-list').textContent,/giữ nguyên/);assert.doesNotMatch($('#notification-list').textContent,/sao lưu rồi thu hồi/);
});

test('owned pending upload can be cancelled without submitting the required file form; quota uses selected profile',async()=>{
 const {context,$}=setup();const storage=new Map([['cloudhub_access_token',token([])]]);
 globalThis.sessionStorage={getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)};
 globalThis.location={search:'',pathname:'/',hash:'',assign(){}};globalThis.history={replaceState(){}};window.CLOUDHUB={...context.cfg,apiBase:'https://api.example'};
 const eid='env-owned',pending={upload_id:'upload-owned',key:'pending.txt',can_cancel:true};let cancelled=false;
 const values={'/account':{email_verified:true,role:'user'},'/templates':{items:[]},'/environments':{items:[{environment_id:eid,template_id:'T07',status:'READY',lock:'upload-owned'}]},'/recovery-points':{items:[]},'/limits':quota,'/notifications':{items:[]},'/operations':{items:[]}};
 globalThis.fetch=async(url,options={})=>{
  const path=new URL(url,'https://api.example').pathname;
  if(path==='/ui-context')return {ok:true,json:async()=>({country_code:'VN'})};
  if(path==='/account/preferences')return {ok:true,json:async()=>({language_preference:'vi'})};
  if(path.endsWith('/files'))return {ok:true,json:async()=>({items:[],writes_used:2,direct_upload_enabled:true,write_enabled:true,limits:{max_files:100,max_file_bytes:5242880,max_total_bytes:52428800,max_writes:256},pending_upload:cancelled?null:pending})};
  if(path.endsWith('/uploads/upload-owned/cancel')){cancelled=true;return {ok:true,json:async()=>({status:'CANCELLED'})};}
  assert.ok(values[path],'unexpected '+path);return {ok:true,json:async()=>values[path]};
 };
 const timer=globalThis.setInterval;globalThis.setInterval=()=>1;
 try{
  await loadApp();await flush();[...$('#environments').querySelectorAll('button')].find(b=>b.textContent==='Quản lý file').click();await flush();
  assert.match($('#file-list').textContent,/2\/256/);
  const cancel=$('#file-release-controls button');assert.equal(cancel.type,'button');cancel.click();await flush();
  assert.equal(cancelled,true);assert.equal($('#file-input').value,'');assert.doesNotMatch($('#file-progress').textContent,/pending.txt/);
 }finally{globalThis.setInterval=timer;}
});

for(const templateId of ['T03','T09'])test('data cockpit keeps the accepted operation visible, blocks repeat commands and renders results: '+templateId,async()=>{
 const {context,$}=setup();window.CLOUDHUB={...context.cfg,apiBase:'https://api.example'};
 const storage=new Map([['cloudhub_access_token',token([])]]);globalThis.localStorage=undefined;
 globalThis.sessionStorage={getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)};
 globalThis.location={search:'',pathname:'/',hash:'',assign(){}};globalThis.history={replaceState(){}};
 const op={operation_id:'op-local-data',environment_id:'env-owned',action:'list_records',status:'RUNNING',phase:'USE_DATA'},commands=[];
 const values={'/account':{email_verified:true,role:'user'},'/templates':{items:[]},'/environments':{items:[{environment_id:'env-owned',template_id:templateId,status:'READY'}]},'/recovery-points':{items:[]},'/limits':quota,'/notifications':{items:[]},'/operations':{items:[]}};
 if(templateId==='T09')values['/environments'].items[0].access_address='https://owned-api.example/records';
 globalThis.fetch=async(url,options={})=>{const path=new URL(url,'https://api.example').pathname;
  if(String(url)==='https://owned-api.example/records'){assert.ok(options.headers.Authorization.startsWith('Bearer '));return {ok:true,json:async()=>({items:[{record_id:'jwt-read',text:'owned response'}]})};}
  if(path==='/ui-context')return {ok:true,json:async()=>({country_code:'VN'})};
  if(path==='/account/preferences')return {ok:true,json:async()=>({language_preference:'vi'})};
  if(path.endsWith('/list_records')){commands.push(options);return {ok:true,json:async()=>structuredClone(op)};}
  assert.ok(values[path],'unexpected '+path);return {ok:true,json:async()=>structuredClone(values[path])};
 };
 const timer=globalThis.setInterval;globalThis.setInterval=()=>1;
 try{await loadApp();await flush();const {t}=await import('../frontend/i18n.js');[...$('#environments').querySelectorAll('button')].find(b=>b.textContent===t('ui.0ce3732c6c81')).click();
  $('#record-read').click();await flush();assert.equal($('#records-dialog').open,true);assert.equal($('#record-read').disabled,true);assert.equal(commands.length,1);assert.ok(commands[0].headers['Idempotency-Key']);
  op.status='SUCCEEDED';op.phase='DONE';op.result={items:[{record_id:'owned-1',text:'<script>untrusted</script>'}]};values['/operations'].items=[op];$('#refresh').click();await flush();
  assert.equal($('#record-read').disabled,false);assert.match($('#record-result').textContent,/owned-1/);assert.equal($('#record-result script'),null);assert.match($('#record-result').textContent,/<script>/);
  if(templateId==='T09'){$('#record-close').click();[...$('#environments').querySelectorAll('button')].find(b=>b.textContent===t('ui.bfbaad232cbe')).click();await flush();assert.match($('#record-result').textContent,/jwt-read/);assert.doesNotMatch($('#notice').textContent,/jwt-read/);
   $('#record-text').value='private draft';$('#ssh-command').value='private host';$('#logout').click();await flush();assert.equal($('#record-result').textContent,'');assert.equal($('#record-text').value,'');assert.equal($('#ssh-command').value,'');
  }
 }finally{globalThis.setInterval=timer;}
});
