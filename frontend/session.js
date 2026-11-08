import {claims,refreshCognito} from './auth.js';
import {t as tr} from './i18n.js';

// Matches the current Cognito app client's one-day refresh validity. This is
// an absolute window, not a sliding timeout. Passwords never enter storage.
export const SESSION_WINDOW_MS=24*60*60*1000;
export const AUTH_KEYS=Object.freeze({tab:'cloudhub.auth.tab.v1',remember:'cloudhub.auth.remember.v1',epoch:'cloudhub.auth.epoch.v1'});
const legacy=['cloudhub_access_token','cloudhub_refresh_token','cloudhub_auth_method'];
const storage=name=>{try{return globalThis[name];}catch{return null;}};
const get=(store,key)=>{try{return store?.getItem(key)||null;}catch{return null;}};
const put=(store,key,value)=>{try{store?.setItem(key,value);return store?.getItem(key)===value;}catch{return false;}};
const remove=(store,key)=>{try{store?.removeItem(key);}catch{/* Memory-only sessions still work. */}};
const parse=value=>{try{return JSON.parse(value);}catch{return null;}};
const sessionError=()=>Object.assign(Error(tr('session.expired')),{code:'SESSION_EXPIRED'});

export function createSession({cfg,tab=storage('sessionStorage'),persistent=storage('localStorage'),now=Date.now,
  refresh=refreshCognito,eventTarget=globalThis.window,onChange=()=>{},onExternalChange=()=>{}}){
  let record=null,generation=0,pending=null;
  const epoch=()=>get(persistent,AUTH_KEYS.epoch)||'initial';
  function tokenIdentity(token){
    const value=claims(token);
    if(value.token_use!=='access'||value.client_id!==cfg.clientId||!value.sub||
      typeof value.iss!=='string'||!value.iss.startsWith('https://cognito-idp.'+cfg.region+'.amazonaws.com/')||
      !Number.isFinite(Number(value.exp)))throw sessionError();
    return value;
  }
  function valid(value){
    return value?.version===1&&value.clientId===cfg.clientId&&value.region===cfg.region&&
      typeof value.id==='string'&&typeof value.identity?.sub==='string'&&typeof value.identity?.iss==='string'&&
      ['api','oauth'].includes(value.method)&&value.epoch===epoch()&&
      Number.isFinite(value.startedAt)&&Number.isFinite(value.expiresAt)&&value.startedAt<=now()+60000&&
      value.expiresAt>now()&&value.expiresAt<=value.startedAt+SESSION_WINDOW_MS&&
      (value.refresh_token===null||typeof value.refresh_token==='string');
  }
  function notify(){onChange(record?.access_token||null);}
  function persist(){
    if(!record)return;
    if(record.remember){
      // Keep access JWTs in the tab only; the persistent record needs only the
      // refresh token and identity binding to restore through Cognito.
      const {access_token,...remembered}=record;
      record.remember=put(persistent,AUTH_KEYS.remember,JSON.stringify(remembered));
    }
    put(tab,AUTH_KEYS.tab,JSON.stringify(record));
  }
  function clear({broadcast=true}={}){
    const old=record;generation++;record=null;pending=null;
    remove(tab,AUTH_KEYS.tab);remove(tab,'pkce');for(const key of legacy)remove(tab,key);
    if(broadcast){remove(persistent,AUTH_KEYS.remember);put(persistent,AUTH_KEYS.epoch,crypto.randomUUID());}
    notify();return old;
  }
  function clearOwn(){
    const latest=parse(get(persistent,AUTH_KEYS.remember));
    clear({broadcast:record?.epoch===epoch()&&(!latest||latest.id===record?.id)});
  }
  function accept(tokens,{remember=true,method='api',startedAt,restoring=false}={}){
    const identity=tokenIdentity(tokens.access_token);
    if(Number(identity.exp)*1000<=now()&&!restoring)throw sessionError();
    // auth_time survives refresh. Migrating a tab cannot extend its original
    // authentication window; Cognito independently enforces refresh expiry.
    const origin=startedAt??Number(identity.auth_time||identity.iat)*1000;
    const start=Number.isFinite(origin)&&origin>0?Math.min(origin,now()):now();
    if(start+SESSION_WINDOW_MS<=now())throw sessionError();
    generation++;pending=null;remove(persistent,AUTH_KEYS.remember);
    record={version:1,id:crypto.randomUUID(),clientId:cfg.clientId,region:cfg.region,epoch:epoch(),method,
      identity:{sub:identity.sub,iss:identity.iss},startedAt:start,expiresAt:start+SESSION_WINDOW_MS,
      access_token:tokens.access_token,refresh_token:tokens.refresh_token||null,remember:!!remember&&!!tokens.refresh_token};
    for(const key of legacy)remove(tab,key);
    persist();notify();return {remembered:record.remember,expiresAt:record.expiresAt};
  }
  function load(){
    const remembered=parse(get(persistent,AUTH_KEYS.remember)),saved=parse(get(tab,AUTH_KEYS.tab));
    if(valid(remembered)&&remembered.refresh_token){
      record=valid(saved)&&saved.id===remembered.id?{...saved,refresh_token:remembered.refresh_token}:{...remembered,access_token:null};
    }else if(valid(saved)&&!saved.remember)record=saved;
    else{
      remove(tab,AUTH_KEYS.tab);if(remembered)remove(persistent,AUTH_KEYS.remember);
      const oldAccess=get(tab,legacy[0]),oldRefresh=get(tab,legacy[1]),oldMethod=get(tab,legacy[2])||'oauth';
      if(oldAccess){try{accept({access_token:oldAccess,refresh_token:oldRefresh},{remember:!!oldRefresh,method:oldMethod,restoring:true});}catch{for(const key of legacy)remove(tab,key);}}
    }
    if(record?.access_token){try{const value=tokenIdentity(record.access_token);if(value.sub!==record.identity.sub||value.iss!==record.identity.iss)throw sessionError();}catch{clear();}}
  }
  function stillCurrent(id,run){
    if(!record||record.id!==id||generation!==run||!valid(record))return false;
    if(record.remember&&parse(get(persistent,AUTH_KEYS.remember))?.id!==id)return false;
    return true;
  }
  async function ensure(){
    if(!record)throw sessionError();
    if(!stillCurrent(record.id,generation)){clearOwn();throw sessionError();}
    if(record.access_token&&Number(tokenIdentity(record.access_token).exp)*1000>now()+60000)return record.access_token;
    if(!record.refresh_token){clear();throw sessionError();}
    if(!pending){
      const before=record,run=generation;
      const task=(async()=>{
        try{
          let value;
          if(before.method==='api')value=await refresh(cfg,before.refresh_token,before.access_token);
          else{
            const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),15000);
            try{
              const response=await fetch(cfg.cognitoDomain+'/oauth2/token',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},
                body:new URLSearchParams({grant_type:'refresh_token',client_id:cfg.clientId,refresh_token:before.refresh_token}),signal:controller.signal});
              if(!response.ok)throw Object.assign(Error(tr('session.retry')),{code:response.status===400||response.status===401?'NotAuthorizedException':'SESSION_NETWORK'});
              value=await response.json();
            }finally{clearTimeout(timeout);}
          }
          if(!stillCurrent(before.id,run))throw sessionError();
          const after=tokenIdentity(value.access_token);
          if(after.sub!==before.identity.sub||after.iss!==before.identity.iss||Number(after.exp)*1000<=now())throw Object.assign(sessionError(),{code:'SESSION_IDENTITY'});
          record={...before,access_token:value.access_token,refresh_token:value.refresh_token||before.refresh_token};
          persist();notify();return record.access_token;
        }catch(error){
          if(record?.id===before.id&&generation===run&&['NotAuthorizedException','UserNotFoundException','SESSION_EXPIRED','SESSION_IDENTITY'].includes(error.code))clearOwn();
          throw error;
        }
      })();
      pending=task;task.finally(()=>{if(pending===task)pending=null;}).catch(()=>{});
    }
    return pending;
  }
  function changed(event){
    if(event.storageArea&&event.storageArea!==persistent)return;
    if(event.key!==null&&!Object.values(AUTH_KEYS).includes(event.key))return;
    if(!record)return;
    const latest=parse(get(persistent,AUTH_KEYS.remember));
    if(record.epoch!==epoch()||(record.remember&&latest?.id!==record.id)||(!record.remember&&valid(latest)&&latest.id!==record.id)){
      clear({broadcast:false});onExternalChange();
    }
  }
  load();eventTarget?.addEventListener('storage',changed);
  return {accept,ensure,clear,hasSession:()=>!!record,id:()=>record?.id||null,identity:()=>record?{...record.identity}:null,token:()=>record?.access_token||null,
    invalidate:token=>{if(record?.access_token===token)clearOwn();},
    dispose:()=>eventTarget?.removeEventListener('storage',changed)};
}
