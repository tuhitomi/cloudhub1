import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {parseHTML} from 'linkedom';
import {createPublicPreview} from '../frontend/public-preview.js';
import {validRumConfig,rumOptions,startRum} from '../frontend/rum.js';

const html=await fs.readFile(new URL('../frontend/index.html',import.meta.url),'utf8');
const catalog={items:[{template_id:'static-site',regions:[]}],signup_policy:{max_active:2,budget_milliusd:5000}};
const ok=body=>({ok:true,status:200,json:async()=>body});
function page(origin){
 const {window}=parseHTML(html);globalThis.document=window.document;globalThis.window=window;
 Object.defineProperty(globalThis,'location',{configurable:true,value:origin?{origin}:undefined});
}
const cfg={configured:true,apiBase:'https://api.cloudhub1.me',redirectUri:'https://cloudhub1.me/'};
const rum={appMonitorId:'3437dfd6-b89e-4f61-b230-485ec03380da',identityPoolId:'ap-southeast-1:a00f0573',guestRoleArn:'arn:aws:iam::123456789012:role/guest',region:'ap-southeast-1',sessionSampleRate:1};

test('catalog goes through the edge-cached same-origin path on the production site',async()=>{
 page('https://cloudhub1.me');const urls=[];
 const view=createPublicPreview({cfg,login(){},fetcher:async url=>{urls.push(url);return ok(catalog);}});
 assert.equal((await view.load()).items.length,1);
 assert.deepEqual(urls,['https://cloudhub1.me/public/catalog']);
});

test('catalog falls back to the API when the edge path fails or answers an error',async()=>{
 for(const edge of [async()=>{throw TypeError('network');},async()=>({ok:false,status:503})]){
  page('https://cloudhub1.me');const urls=[];
  const view=createPublicPreview({cfg,login(){},fetcher:async url=>{urls.push(url);return url.startsWith('https://cloudhub1.me')?edge():ok(catalog);}});
  await view.load();
  assert.deepEqual(urls,['https://cloudhub1.me/public/catalog','https://api.cloudhub1.me/public/catalog']);
 }
});

test('other origins (local development, previews) call the API directly',async()=>{
 for(const origin of ['http://localhost:8080','https://preview.example',undefined]){
  page(origin);const urls=[];
  const view=createPublicPreview({cfg,login(){},fetcher:async url=>{urls.push(url);return ok(catalog);}});
  await view.load();
  assert.deepEqual(urls,['https://api.cloudhub1.me/public/catalog'],String(origin));
 }
});

test('index.html loads the optional RUM bootstrap as a module',()=>{
 assert.match(html,/<script type="module" src="rum.js"><\/script>/);
});

test('RUM config must name the monitor, identity pool, guest role and Region',()=>{
 assert.equal(validRumConfig(rum),true);
 for(const key of ['appMonitorId','identityPoolId','guestRoleArn','region'])assert.equal(validRumConfig({...rum,[key]:''}),false,key);
 assert.equal(validRumConfig({...rum,region:'singapore'}),false);
 assert.equal(validRumConfig({...rum,sessionSampleRate:2}),false);
 assert.equal(validRumConfig(null),false);
 const options=rumOptions(rum);
 assert.equal(options.endpoint,'https://dataplane.rum.ap-southeast-1.amazonaws.com');
 assert.deepEqual(options.telemetries,['performance','errors']);
 assert.equal(options.allowCookies,false);
});

function fakeWindow(){
 const appended=[];
 return {appended,document:{createElement:tag=>({tag}),head:{append:node=>appended.push(node)}}};
}

test('RUM does nothing without a deployed rum-config.json',async()=>{
 for(const fetcher of [async()=>({ok:false,status:403}),async()=>{throw TypeError('offline');},async()=>ok({...rum,region:'bad'})]){
  const win=fakeWindow();
  assert.equal(await startRum({win,fetcher}),false);
  assert.equal(win.AwsRumClient,undefined);assert.deepEqual(win.appended,[]);
 }
});

test('RUM queues commands and loads the self-hosted client once',async()=>{
 const win=fakeWindow();const urls=[];
 assert.equal(await startRum({win,fetcher:async url=>{urls.push(url);return ok(rum);}}),true);
 assert.deepEqual(urls,['rum-config.json']);
 assert.equal(win.AwsRumClient.i,rum.appMonitorId);assert.equal(win.AwsRumClient.r,'ap-southeast-1');
 assert.equal(win.appended.length,1);assert.equal(win.appended[0].src,'vendor/aws-rum-web/cwr.js');assert.equal(win.appended[0].async,true);
 win.cwr('recordEvent',{x:1});assert.deepEqual(win.AwsRumClient.q,[{c:'recordEvent',p:{x:1}}]);
 assert.equal(await startRum({win,fetcher:async()=>ok(rum)}),false);
 assert.equal(win.appended.length,1);
});
