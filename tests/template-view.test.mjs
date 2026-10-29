import {test} from 'node:test';
import assert from 'node:assert/strict';
import {parseHTML} from 'linkedom';
import {setLanguage} from '../frontend/i18n.js';
import {appendTemplateViewer} from '../frontend/template-view.js';
const EID='env-'+'a'.repeat(24);
const value=()=>({environment_id:EID,source:'AWS_CLOUDFORMATION_ORIGINAL',read_only:true,redacted:true,deployable:false,region:'ap-southeast-1',retrieved_at:1000,view_sha256:'a'.repeat(64),redaction_count:2,template:{Resources:{Machine:{Type:'AWS::EC2::Instance'}}},resources:[{logical_id:'Machine',resource_type:'AWS::EC2::Instance'}]});
const tick=()=>new Promise(resolve=>setImmediate(resolve));
function fixture(api){
 const {document}=parseHTML('<html><body><main></main></body></html>');
 const host=document.querySelector('main');const element=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
 return {host,...appendTemplateViewer(host,{environment_id:EID},{api,element,timestamp:x=>String(x)})};
}
test('template read is lazy, read-only, text-safe and reused when reopening',async()=>{
 await setLanguage('en',{persist:false});let calls=[];
 const v=value();v.resources[0].logical_id='<img src=x onerror=alert(1)>';
 const ui=fixture(async(...args)=>{calls.push(args);return v;});assert.equal(calls.length,0);
 ui.button.click();await tick();assert.equal(calls.length,1);assert.equal(calls[0][0],'/environments/'+EID+'/template');assert.equal(calls[0].length,1);
 assert.equal(ui.host.querySelectorAll('img,textarea,input,[contenteditable]').length,0);assert.ok(ui.host.textContent.includes('<img'));
 assert.equal(ui.host.querySelector('pre').textContent,JSON.stringify(v.template,null,2));assert.equal(ui.button.getAttribute('aria-expanded'),'true');
 ui.button.click();ui.button.click();await tick();assert.equal(calls.length,1);
});
test('closing fences stale results, reopening fetches only the current view',async()=>{
 let resolve,calls=0;const ui=fixture(()=>{calls++;return new Promise(r=>resolve=r);});
 ui.button.click();ui.button.click();resolve(value());await tick();assert.equal(ui.host.querySelector('pre'),null);
 ui.button.click();resolve(value());await tick();assert.equal(calls,2);assert.ok(ui.host.querySelector('pre'));
});
test('AWS error is explained without provider text and retry is explicit',async()=>{
 await setLanguage('vi',{persist:false});let attempts=0;
 const ui=fixture(async()=>{if(!attempts++)throw {code:'TEMPLATE_ACCESS_UNAVAILABLE',message:'secret stack trace'};return value();});
 ui.button.click();await tick();assert.match(ui.host.textContent,/chưa có quyền đọc/);assert.ok(!ui.host.textContent.includes('secret stack trace'));
 const retry=ui.panel.querySelector('button');assert.equal(retry.hidden,false);retry.click();await tick();assert.equal(attempts,2);assert.ok(ui.host.querySelector('pre'));
});
test('wrong environment and detached details never display a response',async()=>{
 const ui=fixture(async()=>({...value(),environment_id:'env-other'}));ui.button.click();await tick();assert.equal(ui.host.querySelector('pre'),null);
 let resolve;const detached=fixture(()=>new Promise(r=>resolve=r));detached.button.click();detached.host.replaceChildren();resolve(value());await tick();assert.equal(detached.host.querySelector('pre'),null);
});
