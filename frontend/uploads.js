import {t} from './i18n.js';
// Capability URLs stay in memory. Retries retain the exact grant/operation key.
export function createUploader({post,keyFor,xhrFactory=()=>new XMLHttpRequest(),now=()=>Date.now(),storage=(()=>{try{return globalThis.sessionStorage}catch{return null}})()}){
 const pending=new Map(),attempts=new Map();
 const storageKey='cloudhub.pending_uploads';
 try{for(const row of JSON.parse(storage?.getItem(storageKey)||'[]'))if(row?.intent&&row.body&&row.requestKey&&row.completeKey){const {intent,body,scope,environment,requestKey,completeKey,cancelKey,uploadId,expiresAt,completeUntil,uploaded}=row;pending.set(intent,{intent,body,scope,environment,requestKey,completeKey,cancelKey,uploadId,expiresAt,completeUntil,uploaded,grant:null});}}catch{/* Corrupt or unavailable storage never changes backend ownership checks. */}
 function persist(){try{storage?.setItem(storageKey,JSON.stringify([...pending.values()].slice(-20).map(({intent,body,scope,environment,requestKey,completeKey,cancelKey,uploadId,expiresAt,completeUntil,uploaded})=>({intent,body,scope,environment,requestKey,completeKey,cancelKey,uploadId,expiresAt,completeUntil,uploaded}))));}catch{/* The owned listing still permits cancellation without browser storage. */}}
 function accepted(state,op,onProgress){pending.delete(state.intent);persist();onProgress(100);return op;}
 const upload=async function upload({environment,file,key,contentType,releaseId,expectedVersion,onProgress=()=>{}}){
  const bytes=await file.arrayBuffer();
  if(releaseId&&/html|css|javascript/.test(contentType)){
   const text=new TextDecoder('utf-8',{fatal:true}).decode(bytes),match=text.match(/(?:["'`(=]\s*)(\/(?!\/)[^"'`\s)<>]{0,160})/);
   if(match||/<base\b/i.test(text))throw Object.assign(Error(t('release.invalidReference',{file:key,path:match?match[1].split(/[?#]/)[0].slice(0,128):'<base>'})),{code:'RELEASE_UNVERSIONED_REFERENCE',file:key,asset_path:match?match[1].split(/[?#]/)[0].slice(0,128):'<base>'});
  }
  const hash=await crypto.subtle.digest('SHA-256',bytes);
  const digest=[...new Uint8Array(hash)].map(x=>x.toString(16).padStart(2,'0')).join('');
  const body={key,size:file.size,sha256:digest,content_type:contentType,...(releaseId?{release_id:releaseId}:{}),...(expectedVersion?{expected_version:expectedVersion}:{})};
  const intent=environment+'/'+JSON.stringify(body);let state=pending.get(intent);
  const scope=state?.scope||environment+'/upload/'+JSON.stringify(body)+'/attempt/'+(attempts.get(intent)||0);
  if(!state){state={body,scope,intent,grant:null,uploaded:false,environment,requestKey:keyFor(scope),completeKey:keyFor(scope+'/complete'),cancelKey:keyFor(scope+'/cancel')};pending.set(intent,state);persist();}
  if(state.uploadId&&!state.grant){
   try{return accepted(state,await post('/environments/'+environment+'/uploads/'+state.uploadId+'/complete',{},state.completeKey),onProgress);}
   catch(error){if(!['UPLOAD_INCOMPLETE','UPLOAD_NOT_VISIBLE'].includes(error.code))throw error;if(now()>=state.expiresAt*1000)throw Object.assign(Error(t('upload.expired')),{code:'UPLOAD_EXPIRED'});state.uploaded=false;}
  }
  if(!state.grant){state.grant=await post('/environments/'+environment+'/uploads',state.body,state.requestKey);state.uploadId=state.grant.upload_id;state.expiresAt=state.grant.expires_at;state.completeUntil=state.grant.complete_until;persist();}
  const grant=state.grant;
  if(!state.uploaded){
   if(now()>=grant.expires_at*1000)throw Object.assign(Error(t('upload.expired')),{code:'UPLOAD_EXPIRED'});
   const form=new FormData();for(const [name,value]of Object.entries(grant.post.fields))form.append(name,value);form.append('file',file);
   await new Promise((resolve,reject)=>{const xhr=xhrFactory();xhr.open('POST',grant.post.url);xhr.timeout=120000;
    xhr.upload.onprogress=e=>onProgress(e.lengthComputable?Math.min(99,Math.round(e.loaded/e.total*100)):null);
    xhr.onload=()=>xhr.status>=200&&xhr.status<300?resolve():reject(Error(t('upload.failed')));
    xhr.onerror=xhr.ontimeout=()=>reject(Error(t('upload.retry')));xhr.send(form);});
   state.uploaded=true;persist();
  }
  const op=await post('/environments/'+environment+'/uploads/'+grant.upload_id+'/complete',{},state.completeKey);
  return accepted(state,op,onProgress);
 };
 upload.cancel=async (environment,ownedPendingId)=>{
  const state=[...pending.values()].find(x=>x.environment===environment&&(!ownedPendingId||x.uploadId===ownedPendingId)),uid=ownedPendingId||state?.uploadId;if(!uid)return null;
  const result=await post('/environments/'+environment+'/uploads/'+uid+'/cancel',{},state?.cancelKey||keyFor(environment+'/cancel/'+uid));
  if(!result.operation_id&&state){pending.delete(state.intent);attempts.set(state.intent,(attempts.get(state.intent)||0)+1);persist();}return result;
 };
 upload.reconcile=(environment,pendingId)=>{for(const [key,row]of pending)if(row.environment===environment&&(!pendingId||row.uploadId&&row.uploadId!==pendingId))pending.delete(key);persist();};
 return upload;
}
