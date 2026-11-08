import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {parseHTML} from 'linkedom';
import {setLanguage,disposeLanguageUI} from '../frontend/i18n.js';
import {createCognitoAuth,createRegistration} from '../frontend/auth.js';
import {installAppearance} from '../frontend/appearance.js';
import {createPublicPreview} from '../frontend/public-preview.js';
import {architecture} from '../frontend/architecture.js';
const html=await fs.readFile(new URL('../frontend/index.html',import.meta.url),'utf8');
const cfg={configured:true,apiBase:'https://api.example',region:'ap-southeast-1',clientId:'client123'};
const flush=async()=>{for(let i=0;i<8;i++)await new Promise(r=>setImmediate(r));};
function dom(){
 disposeLanguageUI();const {window}=parseHTML(html);globalThis.document=window.document;globalThis.window=window;
 Object.defineProperty(window.HTMLSelectElement.prototype,'value',{configurable:true,get(){return this._selected??this.querySelector('option')?.value??'';},set(v){this._selected=String(v);}});
 for(const d of document.querySelectorAll('dialog')){Object.defineProperty(d,'open',{get(){return d.hasAttribute('open');}});d.showModal=()=>d.setAttribute('open','');d.close=()=>d.removeAttribute('open');}
 for(const f of document.querySelectorAll('form'))f.reset=()=>{for(const i of f.querySelectorAll('input'))i.value='';};
 return s=>document.querySelector(s);
}
test('auth forms switch in both directions, retaining email and clearing passwords without authentication',async()=>{
 const $=dom();await setLanguage('vi',{persist:false});const calls=[];globalThis.fetch=async()=>{calls.push('unexpected');throw Error();};let auth,registration;
 auth=createCognitoAuth({cfg,onAuthenticated:()=>{},onSignup:email=>registration.open(email)});
 registration=createRegistration({cfg,onConfirmed:()=>{},onSignin:email=>auth.open(email)});
 auth.open();$('#login-email').value='new@example.com';$('#login-password').value='local-only';$('#login-to-signup').click();
 assert.equal($('#login-dialog').open,false);assert.equal($('#signup-dialog').open,true);assert.equal($('#signup-email').value,'new@example.com');assert.equal($('#login-password').value,'');
 $('#signup-password').value='local-only';$('#signup-password-confirm').value='local-only';$('#signup-to-login').click();
 assert.equal($('#signup-dialog').open,false);assert.equal($('#login-dialog').open,true);assert.equal($('#login-email').value,'new@example.com');assert.equal($('#signup-password').value,'');assert.equal($('#signup-password-confirm').value,'');assert.deepEqual(calls,[]);
});
test('auth switch remains locked during provider requests and unsupported password challenges',async()=>{
 const $=dom();let done,switched=0;globalThis.fetch=()=>new Promise(r=>done=r);const auth=createCognitoAuth({cfg,onAuthenticated:()=>{},onSignup:()=>switched++});
 auth.open();$('#login-email').value='local@example.com';$('#login-password').value='local-only';const pending=$('#login-form').onsubmit({preventDefault(){}});
 $('#login-to-signup').onclick();assert.equal(switched,0);
 done({ok:true,json:async()=>({Session:'fixture',ChallengeName:'NEW_PASSWORD_REQUIRED',ChallengeParameters:{requiredAttributes:'[]'}})});await pending;
 assert.equal($('#login-to-signup').disabled,true);$('#login-close').click();auth.open();assert.equal($('#login-to-signup').disabled,false);
});
test('new authentication module remains compatible with HTML cached before switch links existed',()=>{
 const $=dom();$('#login-to-signup').remove();$('#signup-to-login').remove();
 const auth=createCognitoAuth({cfg,onAuthenticated(){}}),registration=createRegistration({cfg,onConfirmed(){}});
 auth.open();assert.equal($('#login-dialog').open,true);$('#login-close').click();registration.open();assert.equal($('#signup-dialog').open,true);
});
test('theme persists manual choice, respects system only in auto mode, and survives locale changes',async()=>{
 const $=dom(),store=new Map([['cloudhub.theme','dark']]);let change;const media={matches:false,addEventListener:(name,fn)=>change=fn,removeEventListener(){}};
 const stop=installAppearance({storage:{getItem:k=>store.get(k),setItem:(k,v)=>store.set(k,v)},media});
 assert.equal(document.documentElement.dataset.theme,'dark');change();assert.equal(document.documentElement.dataset.theme,'dark');
 $('#theme-select').value='system';$('#theme-select').dispatchEvent(new window.Event('change'));assert.equal(document.documentElement.dataset.theme,'light');media.matches=true;change();assert.equal(document.documentElement.dataset.theme,'dark');
 $('#theme-select').value='light';$('#theme-select').dispatchEvent(new window.Event('change'));await setLanguage('en',{persist:false});assert.equal(document.documentElement.dataset.theme,'light');assert.equal(store.get('cloudhub.theme'),'light');stop();
});
test('blocked storage does not break theme selection or forms',()=>{
 const $=dom();$('#login-email').value='local@example.com';installAppearance({storage:{getItem(){throw Error();},setItem(){throw Error();}},media:null});$('#theme-select').value='dark';$('#theme-select').dispatchEvent(new window.Event('change'));assert.equal(document.documentElement.dataset.theme,'dark');assert.equal($('#login-email').value,'local@example.com');
});

test('fresh appearance defaults to dark while an existing light preference is respected',()=>{
 for(const saved of [null,'light']){dom();const stop=installAppearance({storage:{getItem:()=>saved,setItem(){throw Error('must not overwrite preference on load');}},media:{matches:false,addEventListener(){},removeEventListener(){}}});assert.equal(document.documentElement.dataset.theme,saved||'dark');stop();}
});
const regions=['ap-southeast-1','ap-northeast-1','us-east-1'];
const catalog={default_region:regions[0],signup_policy:{max_active:2,budget_milliusd:10000},items:[{template_id:'T01',regions:regions.map(region=>({region,configuration_options:[{id:'standard',configuration:{instance_type:'t3.micro',data_gib:8},status:'SUPPORTED'}]}))}]};
const preview=(region,total=500,approved=true)=>({preview:{template_id:'T01',region,profile_id:'standard',hours:1,status:'SUPPORTED',configuration:{instance_type:'t3.micro',vcpu_per_instance:2,memory_gib_per_instance:1,data_gib:8},estimate:{approved,total_milliusd:approved?total:null,currency:'USD',price_updated_at:'2026-10-18T00:00:00Z',units:{ec2_hour:'0.01'},lines:{compute:'0.02'},assumptions:{duration_hours:1}},after_shutdown:{approved:true,total_milliusd:100}}});
test('public preview requests carry no auth, never issue quotes, and display real default policy',async()=>{
 const $=dom();await setLanguage('vi',{persist:false});const calls=[];let logins=0;
 const view=createPublicPreview({cfg,login:()=>logins++,fetcher:async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>url.includes('?')?preview(regions[0]):catalog};}});
 await view.open({template_id:'T01'});assert.match($('#limits-summary').textContent,/2 môi trường/);assert.match($('#preview-hardware').textContent,/t3.micro/);assert.match($('#preview-cost').textContent,/0,500/);assert.equal($('#create-dialog').open,false);
 for(const request of calls){assert.equal(request.options.headers.Authorization,undefined);assert.equal(request.options.credentials,'omit');assert.equal(request.options.method,undefined);assert.match(request.url,/\/public\/catalog/);}
 $('#preview-login').click();assert.equal(logins,1);assert.equal($('#preview-dialog').open,false);
});
test('late regional preview cannot overwrite the new Region, and switching language preserves its selection',async()=>{
 const $=dom();await setLanguage('en',{persist:false});const responses=[];
 const view=createPublicPreview({cfg,login(){},fetcher:async url=>url.includes('?')?new Promise(resolve=>responses.push({url,resolve})):({ok:true,json:async()=>catalog})});
 const first=view.open({template_id:'T01'});await flush();$('#preview-region').value=regions[1];$('#preview-region').onchange();await flush();
 responses[1].resolve({ok:true,json:async()=>preview(regions[1],900)});await flush();responses[0].resolve({ok:true,json:async()=>preview(regions[0],100)});await first;await flush();
 assert.match($('#preview-cost').firstChild.textContent,/0\.900/);assert.doesNotMatch($('#preview-cost').firstChild.textContent,/0\.100/);await setLanguage('vi',{persist:false});assert.equal($('#preview-region').value,regions[1]);assert.match($('#preview-cost').firstChild.textContent,/0,900/);$('#preview-close').click();
});
test('missing prices remain unknown and an unavailable API permits retry without inventing data',async()=>{
 const $=dom();await setLanguage('vi',{persist:false});let broken=true;
 const view=createPublicPreview({cfg,login(){},fetcher:async url=>url.includes('?')?({ok:true,json:async()=>preview(regions[0],0,false)}):broken?({ok:false,status:503}):({ok:true,json:async()=>catalog})});
 await view.open({template_id:'T01'});assert.equal($('#preview-retry').hidden,false);assert.match($('#preview-status').textContent,/Chưa tải/);
 broken=false;$('#preview-retry').click();await flush();assert.match($('#preview-cost').textContent,/Chưa có đơn giá/);assert.doesNotMatch($('#preview-cost').textContent,/0,000/);$('#preview-close').click();
});
test('all nine service diagrams render safely without internal IDs or T10',()=>{
 const $=dom();for(let i=1;i<=9;i++){architecture($('#preview-architecture'),'T0'+i);assert.equal($('#preview-architecture svg').getAttribute('role'),'img');assert.ok($('#preview-architecture').querySelectorAll('rect').length>=3);assert.equal($('#preview-architecture').querySelector('script'),null);}
 architecture($('#preview-architecture'),'T10');assert.equal($('#preview-architecture').children.length,0);
});
