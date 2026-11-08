import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createSession,AUTH_KEYS,SESSION_WINDOW_MS} from '../frontend/session.js';
const cfg={clientId:'client123',region:'ap-southeast-1',configured:true};
const issuer='https://cognito-idp.ap-southeast-1.amazonaws.com/pool';
const store=()=>{const values=new Map();return {getItem:key=>values.get(key)||null,setItem:(k,v)=>values.set(k,String(v)),removeItem:k=>values.delete(k),values};};
const jwt=(time,extra={})=>'h.'+Buffer.from(JSON.stringify({sub:'alice',iss:issuer,client_id:cfg.clientId,token_use:'access',auth_time:Math.floor(time/1000),exp:Math.floor(time/1000)+3600,...extra})).toString('base64url')+'.sig';
function fixture(){
 let time=Date.now(),calls=0;const persistent=store(),tab=store(),events=new EventTarget();
 const refresh=async()=>{calls++;return {access_token:jwt(time)};};
 const open=(options={})=>createSession({cfg,tab,persistent,eventTarget:events,now:()=>time,refresh,...options});
 const session=open();const tokens=()=>({access_token:jwt(time),refresh_token:'synthetic-refresh-not-a-real-token'});
 return {persistent,tab,events,session,open,tokens,advance:ms=>{time+=ms;},now:()=>time,calls:()=>calls};
}
test('remembered sign-in restores in a new tab through Cognito, with no access JWT persisted',async()=>{
 const f=fixture();f.session.accept(f.tokens());const saved=JSON.parse(f.persistent.getItem(AUTH_KEYS.remember));
 assert.equal(saved.access_token,undefined);assert.equal(saved.password,undefined);
 const next=f.open({tab:store()});assert.equal(next.token(),null);assert.equal(next.hasSession(),true);
 assert.equal((await next.ensure()).split('.').length,3);assert.equal(f.calls(),1);
});
test('unchecking remember retains reload in this tab but not a new tab',async()=>{
 const f=fixture();f.session.accept(f.tokens(),{remember:false});
 assert.equal(f.persistent.getItem(AUTH_KEYS.remember),null);
 assert.equal(f.open().hasSession(),true);assert.equal(f.open({tab:store()}).hasSession(),false);
});
test('refresh does not slide the absolute 24-hour authentication window',async()=>{
 const f=fixture();f.session.accept(f.tokens());const original=JSON.parse(f.persistent.getItem(AUTH_KEYS.remember)).expiresAt;
 f.advance(3600000);await f.session.ensure();assert.equal(JSON.parse(f.persistent.getItem(AUTH_KEYS.remember)).expiresAt,original);
 f.advance(SESSION_WINDOW_MS);await assert.rejects(f.session.ensure(),{code:'SESSION_EXPIRED'});
 assert.equal(f.persistent.getItem(AUTH_KEYS.remember),null);assert.equal(f.session.token(),null);
});
test('expired persistent state cannot revive an old tab',async()=>{
 const f=fixture();f.session.accept(f.tokens());f.advance(SESSION_WINDOW_MS+1000);
 assert.equal(f.open().hasSession(),false);assert.equal(f.open({tab:store()}).hasSession(),false);assert.equal(f.calls(),0);
});
test('one refresh serves concurrent requests in a tab',async()=>{
 const f=fixture();f.session.accept(f.tokens());f.advance(3600000);
 const results=await Promise.all([f.session.ensure(),f.session.ensure(),f.session.ensure()]);
 assert.equal(new Set(results).size,1);assert.equal(f.calls(),1);
});
test('temporary network failure preserves the saved session and permits retry',async()=>{
 const f=fixture();f.session.accept(f.tokens());let attempts=0;
 const next=f.open({tab:store(),refresh:async()=>{if(++attempts===1)throw new TypeError('synthetic offline');return {access_token:jwt(f.now())};}});
 await assert.rejects(next.ensure(),TypeError);assert.equal(next.hasSession(),true);assert.ok(f.persistent.getItem(AUTH_KEYS.remember));
 await next.ensure();assert.equal(attempts,2);
});
test('revoked refresh token clears saved and in-memory session',async()=>{
 const f=fixture();f.session.accept(f.tokens());
 const next=f.open({tab:store(),refresh:async()=>{throw Object.assign(Error('synthetic rejected'),{code:'NotAuthorizedException'});}});
 await assert.rejects(next.ensure(),{code:'NotAuthorizedException'});assert.equal(next.hasSession(),false);assert.equal(f.persistent.getItem(AUTH_KEYS.remember),null);
});
test('refresh from a different owner, issuer, client or token type fails closed',async()=>{
 for(const changed of [{sub:'bob'},{iss:issuer+'-other'},{client_id:'wrong'},{token_use:'id'}]){
  const f=fixture();f.session.accept(f.tokens());const next=f.open({tab:store(),refresh:async()=>({access_token:jwt(f.now(),changed)})});
  await assert.rejects(next.ensure());assert.equal(next.hasSession(),false);
 }
});
test('refresh finishing after logout cannot recreate the session',async()=>{
 const f=fixture();f.session.accept(f.tokens());let finish;
 const next=f.open({tab:store(),refresh:()=>new Promise(resolve=>{finish=resolve;})});const pending=next.ensure();
 next.clear();finish({access_token:jwt(f.now())});await assert.rejects(pending,{code:'SESSION_EXPIRED'});
 assert.equal(next.hasSession(),false);assert.equal(f.persistent.getItem(AUTH_KEYS.remember),null);
});
test('refresh finishing after another tab signs out is fenced even before the storage event',async()=>{
 const f=fixture();f.session.accept(f.tokens());let finish;
 const next=f.open({tab:store(),refresh:()=>new Promise(resolve=>{finish=resolve;})});const pending=next.ensure();
 f.session.clear();finish({access_token:jwt(f.now())});await assert.rejects(pending);
 assert.equal(next.token(),null);assert.equal(f.persistent.getItem(AUTH_KEYS.remember),null);
});
test('a late refresh from an old account cannot erase another tab’s newer login',async()=>{
 const f=fixture();f.session.accept(f.tokens());let finish;
 const next=f.open({tab:store(),refresh:()=>new Promise(resolve=>{finish=resolve;})});const pending=next.ensure();
 const newer=jwt(f.now(),{sub:'bob'});f.session.accept({access_token:newer,refresh_token:'newer-synthetic-refresh'});
 finish({access_token:jwt(f.now())});await assert.rejects(pending);
 assert.equal(JSON.parse(f.persistent.getItem(AUTH_KEYS.remember)).identity.sub,'bob');assert.equal(next.hasSession(),false);
});
test('another tab’s logout is checked before returning even an unexpired access token',async()=>{
 const f=fixture();f.session.accept(f.tokens());const next=f.open();f.session.clear();
 await assert.rejects(next.ensure());assert.equal(next.hasSession(),false);
});
test('storage logout clears another tab, preserves unrelated preferences and prevents reload resurrection',async()=>{
 const f=fixture();f.session.accept(f.tokens());let changed=0;const otherTab=store();
 const next=f.open({tab:otherTab,onExternalChange:()=>changed++});await next.ensure();
 f.persistent.setItem('cloudhub.language','de');f.persistent.setItem('cloudhub.theme','dark');otherTab.setItem('upload-journal','keep');
 f.session.clear();const event=new Event('storage');Object.defineProperty(event,'key',{value:AUTH_KEYS.epoch});f.events.dispatchEvent(event);
 assert.equal(next.hasSession(),false);assert.equal(changed,1);assert.equal(f.open({tab:otherTab}).hasSession(),false);
 assert.equal(f.persistent.getItem('cloudhub.language'),'de');assert.equal(f.persistent.getItem('cloudhub.theme'),'dark');assert.equal(otherTab.getItem('upload-journal'),'keep');
});
test('rejected response from an earlier token cannot clear a newer login',()=>{
 const f=fixture();const previous=f.tokens();f.session.accept(previous);const replacement=jwt(f.now(),{sub:'bob'});
 f.session.accept({access_token:replacement,refresh_token:'other-synthetic-refresh'});f.session.invalidate(previous.access_token);
 assert.equal(f.session.token(),replacement);
});
test('blocked persistent storage falls back to this tab without breaking login',async()=>{
 const f=fixture(),blocked={getItem(){throw Error('blocked');},setItem(){throw Error('blocked');},removeItem(){throw Error('blocked');}};
 const session=f.open({persistent:blocked});const saved=session.accept(f.tokens());assert.equal(saved.remembered,false);assert.ok(await session.ensure());
 assert.equal(f.open({persistent:blocked}).hasSession(),true);
});
test('no browser storage still supports an in-memory login',async()=>{
 const f=fixture(),session=f.open({tab:null,persistent:null});assert.equal(session.accept(f.tokens()).remembered,false);assert.ok(await session.ensure());session.clear();assert.equal(session.token(),null);
});
test('legacy session migrates once, including an expired access JWT with a valid refresh window',async()=>{
 const f=fixture(),original=f.tokens();f.tab.setItem('cloudhub_access_token',original.access_token);f.tab.setItem('cloudhub_refresh_token',original.refresh_token);f.tab.setItem('cloudhub_auth_method','api');
 f.advance(3601000);const session=f.open();assert.equal(session.hasSession(),true);assert.ok(await session.ensure());
 assert.equal(f.tab.getItem('cloudhub_refresh_token'),null);const saved=JSON.parse(f.persistent.getItem(AUTH_KEYS.remember));
 assert.ok(saved.expiresAt<=f.now()-3601000+SESSION_WINDOW_MS);assert.equal(f.calls(),1);
});
test('configuration or malformed state cannot restore a session',()=>{
 const f=fixture();f.session.accept(f.tokens());
 assert.equal(f.open({tab:store(),cfg:{...cfg,clientId:'different'}}).hasSession(),false);
 f.persistent.setItem(AUTH_KEYS.remember,'{broken');assert.equal(f.open({tab:store()}).hasSession(),false);
});
test('legacy token without the expected Cognito identity is discarded',()=>{
 const f=fixture();f.tab.setItem('cloudhub_access_token',jwt(f.now(),{client_id:'wrong'}));
 assert.equal(f.open().hasSession(),false);assert.equal(f.tab.getItem('cloudhub_access_token'),null);
});
