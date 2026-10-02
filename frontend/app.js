import {renderWorkspaceDashboard,renderWorkspaceEnvironments,renderWorkspaceDetailTools} from './workspace-view.js';
import {appendCleanupReport,backupAvailability,explainDisabled,restoreReview} from './product-view.js';
import {createUploader} from './uploads.js';
import {templateText,backupScope,profileLabel} from './catalog-text.js';
import {errorText} from './error-text.js';
import {t as tr} from './i18n.js';
import {initializeLanguage,installLanguageUI,accountLanguage,onLanguageChange,date,money} from './i18n.js';
import {installAppearance} from './appearance.js';
import {createPublicPreview} from './public-preview.js';
installLanguageUI();
installAppearance();
const languageReady=initializeLanguage();
import {createPortal} from './portal.js';
import {createLifecycleUI,operatingPolicy,modeName,endingName} from './lifecycle.js';
import {createCognitoAuth,createRegistration,cognitoRequest} from './auth.js';
import {createSession} from './session.js';
import {createRecommendations} from './recommendations.js';
import {createCreationFlow} from './create-flow.js';
import {createJournal} from './create-journal.js';
import {createCreationView} from './create-view.js';
import {operationPresentation,accessInstructions,environmentOverview} from './presentation-data.js';
import {createShellView} from './shell-view.js';
import {createCatalogView} from './catalog-view.js';
import {appendOperationTracker,appendEnvironmentClock,updateClocks,renderReleaseStudio,renderRecordResult,createFileDropZone} from './cockpit.js';
const $ = s => document.querySelector(s);
// Support an older cached HTML shell during a frontend-only rollout. Add only
// missing presentation controls; never replace forms or entered user values.
function ensureCockpitMarkup(){
 const add=(parent,tag,id,text)=>{const node=document.createElement(tag);node.id=id;if(text)node.textContent=text;parent.append(node);return node;};
 const fileForm=$('#file-form');
 if(fileForm&&!$('#file-dropzone')){const zone=add(fileForm,'div','file-dropzone',tr('experience.dropFile'));zone.className='file-dropzone';fileForm.prepend(zone);}
 if(fileForm&&!$('#file-selection')){const selected=add(fileForm,'p','file-selection');selected.setAttribute('role','status');}
 if(!$('#files-title')&&$('#files-dialog h2'))$('#files-dialog h2').id='files-title';
 if($('#records-dialog')&&!$('#record-result')){const result=add($('#records-dialog'),'div','record-result');result.className='data-result';result.setAttribute('role','region');result.setAttribute('aria-label',tr('experience.dataExplorer'));}
 if(!$('#ssh-dialog')){const dialog=add(document.body,'dialog','ssh-dialog');dialog.setAttribute('aria-labelledby','ssh-title');add(dialog,'h2','ssh-title',tr('experience.sshTitle'));
  const label=add(dialog,'label','ssh-command-label',tr('experience.sshCommand')),command=add(label,'input','ssh-command');command.readOnly=true;command.setAttribute('translate','no');
  const notice=add(dialog,'p','ssh-notice');notice.setAttribute('role','status');
  for(const [id,key] of [['ssh-copy','experience.copy'],['ssh-close','ui.5d54c2a1a341']])add(dialog,'button',id,tr(key)).type='button';
 }
}
ensureCockpitMarkup();
const cfg = window.CLOUDHUB || {};
let emailVerified=false;
let accessToken=null;
const session=createSession({cfg,onChange:token=>{accessToken=token;},onExternalChange:()=>location.reload()});
accessToken=session.token();
const commands = new Map(), operations = new Map();
let fileEnvironment, recordEnvironment;
let selectedDroppedFile=null,fileBusy=false,fileOpenGeneration=0,recordOperation=null,recordSubmitting=false;
let cachedEnvironments=[];
let overviewLoading=false,overviewError='',overviewUpdated=0,refreshGeneration=0;
const catalogCache=new Map();
let pendingGuestTemplate=null;
// Public descriptions only; authenticated /templates owns availability,
// Regions, configurations and prices. Never put these previews in catalogCache.
const templatePreviews=[
 ['T01',['EC2','EBS']],['T02',['S3','CloudFront']],['T03',['EC2','RDS']],
 ['T04',['ALB','Auto Scaling','RDS']],['T05',['EC2','web server']],
 ['T06',['ECS Fargate']],['T07',['S3']],['T08',['EFS','EC2']],
 ['T09',['API Gateway','Lambda','DynamoDB']]
].map(([template_id,services])=>({template_id,services}));
const stateNames = {PAUSED:tr("ui.a919ce7fbdb6"),PAUSING:tr("ui.e40cc1b782e8"),RESTARTING:tr("ui.75f9ad677614"),READY:tr("ui.d654065d13f4"),PROVISIONING:tr("ui.da7b559f5be4"),BACKING_UP:tr("ui.ed47bc2df524"),RETIRING:tr("ui.37488d76a81a"),DELETED:tr("ui.412c1c534007"),DELETING:tr("ui.07242e5e6f7d"),DELETE_FAILED:tr("ui.75035719dd9a"),RESIDUAL:tr("ui.58ba0d41d54f"),ERROR_RETAINED:tr("ui.b4b193b11b9b"),CREATE_FAILED:tr("ui.667c6ae33cc5"),AVAILABLE:tr("ui.f9950b8958fc"),PENDING:tr("ui.e84898db736f"),FAILED:tr("ui.710b8dc0a898"),EXPIRED:tr("ui.bd2b6fce2633"),EXPIRING:tr("ui.4d76295e32c8")};
function element(tag, text, className){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(className)e.className=className;if(typeof text==='string'&&/^(?:env-|op-|rp-|arn:aws:|https?:)/.test(text))e.setAttribute('translate','no');return e;}
function notice(text){$('#notice').textContent=text;}
function timestamp(sec){return date(sec);}
function button(text,fn,disabled=false){const e=element('button',text);e.type='button';e.disabled=disabled;if([tr("ui.09a233e9990f"),tr("ui.5f805783295c"),tr("ui.c5f4a9a5e7c9")].includes(text))e.dataset.dangerous='true';e.addEventListener('click',()=>Promise.resolve(fn()).catch(showError));return e;}
function showError(err){notice(errorText(err));}
function idempotency(scope){if(!commands.has(scope))commands.set(scope,crypto.randomUUID());return commands.get(scope);}
async function api(path,options={}){
  if(!cfg.configured)throw Object.assign(Error(tr("ui.9e2bc57f1318")),{status:400});
  await ensureToken();const sentToken=accessToken,sentSession=session.id();
  const res=await fetch(cfg.apiBase+path,{...options,headers:{'Authorization':'Bearer '+sentToken,'Content-Type':'application/json',...options.headers}});
  const data=await res.json();
  if(sentSession!==session.id())throw Object.assign(Error(tr('session.expired')),{status:401,code:'SESSION_EXPIRED'});
  if(!res.ok){
    if(res.status===401){session.invalidate(sentToken);if(!session.hasSession())signedOut();}
    throw Object.assign(Error(data.error?.code?errorText(data.error):data.error?.message||tr("ui.4591cd3e135e")+res.status),{status:res.status,code:data.error?.code,reviewRequired:data.error?.review_required===true,field:data.error?.field,file:data.error?.file,asset_path:data.error?.asset_path});
  }
  return data;
}
function post(path,body={},key){return api(path,{method:'POST',body:JSON.stringify(body),headers:key?{'Idempotency-Key':key}:{}});}
function b64(bytes){return btoa(String.fromCharCode(...new Uint8Array(bytes))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=/g,'');}
async function login(){authentication.open();}
const catalogView=createCatalogView({accessInstructions,onSelect:(template,{guest})=>{
 if(guest){pendingGuestTemplate=template.template_id;login().catch(showError);}
 else openCreate(template).catch(showError);
},onPreview:template=>publicPreview.open(template).catch(showError)});
const publicPreview=$('#preview-dialog')?createPublicPreview({cfg,login,isGuest:()=>!accessToken}):{open:login,load:async()=>{}};
async function callback(){const query=new URLSearchParams(location.search);if(query.has('error'))throw Error(tr("ui.da99570cd8df")+query.get('error'));if(!query.has('code'))return;const pkce=JSON.parse(sessionStorage.getItem('pkce')||'null');if(!pkce||query.get('state')!==pkce.state)throw Error(tr("ui.55a234a5771e"));const r=await fetch(cfg.cognitoDomain+'/oauth2/token',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({grant_type:'authorization_code',client_id:cfg.clientId,code:query.get('code'),redirect_uri:cfg.redirectUri,code_verifier:pkce.verifier})});if(!r.ok)throw Error(tr("ui.6459f2ac852d"));const data=await r.json();session.accept(data,{method:'oauth',remember:true});sessionStorage.removeItem('pkce');history.replaceState({},'',location.pathname);}
function signedOut(){
  creation.reset();
  fileOpenGeneration++;selectedDroppedFile=null;fileEnvironment=null;recordEnvironment=null;recordOperation=null;
  fileListing=null;
  document.querySelector('.workspace-detail-tools')?.remove();$('#environment-detail')?.replaceChildren();
  for(const id of ['record-result','record-notice','file-list','file-selection','file-release-controls','ssh-notice'])$('#'+id)?.replaceChildren();
  for(const id of ['record-id','record-text','ssh-command'])if($('#'+id))$('#'+id).value='';
  $('#file-form')?.reset();
  pendingGuestTemplate=null;
  emailVerified=false;refreshGeneration++;cachedEnvironments=[];commands.clear();operations.clear();overviewUpdated=0;overviewError='';overviewLoading=false;
  for(const dialog of document.querySelectorAll('dialog[open]'))dialog.close();
  for(const id of ['environments','backups','operations','environment-history','expiry-notifications','admin-users','admin-environments'])$('#'+id)?.replaceChildren();
  $('#account-settings').hidden=true;$('#admin').hidden=true;$('#login').hidden=false;$('#signup').hidden=false;$('#logout').hidden=true;
  portal.reset();renderCatalog(templatePreviews,{guest:true});renderShell();notice(tr('session.expired'));
}
async function logout(){
  const old=session.clear();signedOut();
  try{if(old?.refresh_token)await cognitoRequest(cfg,'RevokeToken',{ClientId:cfg.clientId,Token:old.refresh_token});}
  catch{/* Local logout is final even if the revocation request cannot connect. */}
  if(old?.method!=='oauth'){location.assign(cfg.redirectUri);return;}
  const u=new URL(cfg.cognitoDomain+'/logout');u.search=new URLSearchParams({client_id:cfg.clientId,logout_uri:cfg.redirectUri});location.assign(u);
}
function renderCatalog(items,{guest=false}={}){
  catalogCache.clear();if(!guest)for(const row of items)catalogCache.set(row.template_id,row);
  catalogView.update(items,{guest});
}
async function loadCatalog(){
  if(!accessToken){renderCatalog(templatePreviews,{guest:true});publicPreview.load().catch(()=>{});return;}
  const host=$('#catalog');host.setAttribute('aria-busy','true');host.replaceChildren(element('p',tr("ui.c5c0d15878d6")));
  try{const {items}=await api('/templates');renderCatalog(items);}
  catch(error){host.replaceChildren(element('p',tr("ui.a7a407ef5679")+error.message),button(tr("ui.a4240dfd28c1"),loadCatalog));throw error;}
  finally{host.setAttribute('aria-busy','false');}
}
const descriptions={
T01:tr("ui.467054bde443"),T02:tr("ui.9a411a36d9f8"),
T03:tr("ui.f28a68c95472"),T04:tr("ui.d74bd45bd464"),
T05:tr("ui.6140ba7ce36a"),T06:tr("ui.028ec7c1dc7b"),
T07:tr("ui.d5db56c81be7"),T08:tr("ui.d21c412765c7"),
T09:tr("ui.c79ba35175bc"),T10:tr("ui.13c80c57008c")};
async function openCreate(t,rp,restoreConfiguration,restoreRegion){if(!accessToken)return login();if(rp){const source=await api('/recovery-points/'+rp);if(!confirm(restoreReview(source)))return;}if(creation.open(catalogCache.get(t.template_id)||t,rp,restoreConfiguration,restoreRegion))$('#create-dialog').showModal();}
function track(op){operations.set(op.operation_id,op);renderOperations();notice(tr("ui.5e23e04f8507")+op.operation_id+tr("ui.67fc8d225627"));}
async function downloadKey(eid){const key=await api('/environments/'+eid+'/ssh-key');const url=URL.createObjectURL(new Blob([key.private_key],{type:'application/x-pem-file'}));const link=element('a');link.href=url;link.download=key.filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);$('#ssh-command').value=key.command;$('#ssh-notice').textContent=tr('experience.sshHelp');$('#ssh-dialog').showModal();}
function renderOperations(){$('#operations').replaceChildren();for(const op of [...operations.values()].sort((a,b)=>Number(b.created_at||0)-Number(a.created_at||0))){const view=operationPresentation(op),card=element('article',undefined,'card');card.dataset.status=op.status;card.append(element('strong',view.title),element('small',op.operation_id),element('p',view.phase),element('p',view.nextStep));appendOperationTracker(card,op);if(op.result&&['put_record','list_records'].includes(op.action)&&op.status==='SUCCEEDED')renderRecordResult(card.appendChild(element('div',undefined,'data-result')),op.result);if(op.error){const code=String(op.error.code||op.error).split(/[;:]/)[0];card.append(element('p',op.error_context?errorText({code:'RELEASE_UNVERSIONED_REFERENCE',...op.error_context}):errorText({code}),'warning'));}if(op.result){const d=element('details');d.append(element('summary',tr("ui.34f4b747ea5c")),element('pre',JSON.stringify(op.result,null,2)));card.append(d);}portal.operationExtras(card,op);$('#operations').append(card);}if(!operations.size)$('#operations').append(element('p',tr("ui.e22339a5bfe6")));updateRecordOperation();}
async function command(eid,action){const scope=eid+'/'+action;track(await post('/environments/'+eid+'/'+action,{},idempotency(scope)));commands.delete(scope);await refresh();}
async function extend(eid){const scope=eid+'/extend';const r=await post('/environments/'+eid+'/extend',{hours:1},idempotency(scope));commands.delete(scope);notice(tr("ui.8ab20c867223")+timestamp(r.deadline));await refresh();}
async function refresh(){
  if(!accessToken)return;
  const run=++refreshGeneration;overviewLoading=true;overviewError='';renderShell();
  try{const [envs,backups]=await Promise.all([api(portal.listPath('/environments')),api('/recovery-points'),portal.refreshOwn()]);
  if(run!==refreshGeneration)return;
  portal.environmentSummary(envs);cachedEnvironments=envs.items;renderEnvironments();portal.renderHistory(cachedEnvironments);
  overviewUpdated=Date.now()/1000;
  if(creation.snapshot().open){Promise.resolve(creation.reconcile({refresh:!document.hidden})).catch(showError);renderCreation(creation.snapshot());}
  $('#backups').replaceChildren();
  for(const rp of backups.items){
    const card=element('article',undefined,'card'),availability=backupAvailability(rp);
    card.append(element('h3',rp.template_id+' · '+(stateNames[rp.status]||rp.status)),element('small',rp.recovery_point),element('p',backupScope(rp)),element('small',['DELETED','DELETING'].includes(rp.status)?tr('ux.backup.DELETED'):tr("ui.f0c6a4beda5a")+timestamp(rp.retain_until)),element('p',rp.restore_verified?tr("ui.e5d0649cc58a"):tr("ui.e9ce2dcd5ec3")));
      card.append(element('p','Region: '+(rp.region||tr("ui.6608c8f339fc"))),button(tr("ui.c652d9c04f95"),()=>openCreate({template_id:rp.template_id,name:rp.template_id},rp.recovery_point,rp.configuration,rp.region),!availability.restore.allowed||!catalogCache.get(rp.template_id)?.create_enabled));
    const restoreButton=card.querySelector('button');explainDisabled(restoreButton,availability.restore.reason||'CONFIGURATION_UNAVAILABLE');
    if(!availability.restore.allowed)card.append(element('p',tr('ux.backup.'+(availability.restore.reason||'UNKNOWN')),'warning'));
    portal.backupExtras(card,rp);$('#backups').append(card);
  }
  if(!backups.items.length)$('#backups').append(element('p',tr("ui.d07fc1d14e9d")));
  }catch(error){if(run===refreshGeneration)overviewError=tr("ui.05f8a29580e9")+error.message+(overviewUpdated?tr("ui.a2bbb3a84fb0"):tr("ui.d2ff18494efd"));throw error;}finally{if(run===refreshGeneration){overviewLoading=false;renderShell();}}
}
function renderEnvironments(){renderWorkspaceEnvironments($('#environments'),portal.filter(cachedEnvironments).filter(e=>e.status!=='DELETED'),{portal,lifecycle,element,button,timestamp,openFiles,openRecords,downloadKey,readOwnedApi,operations,appendOperationTracker,appendCleanupReport,accessInstructions,configurationLabel:environmentConfigurationLabel,onError:showError});}
let fileListing;const directUploader=createUploader({post,keyFor:idempotency});
async function openFiles(env){
  if(fileBusy)return;
  const run=++fileOpenGeneration;
  fileEnvironment=env;
  const data=await api('/environments/'+env.environment_id+'/files');if(run!==fileOpenGeneration)return;fileListing=data;selectedDroppedFile=null;
  $('#file-selection').textContent='';$('#file-dropzone').textContent=tr('experience.dropFile');
  $('#file-dropzone').setAttribute('aria-disabled',String(data.write_enabled===false||!!data.pending_upload));
  $('#files-title').textContent=env.template_id==='T02'?tr('experience.releaseStudio'):tr('ui.84fec93361c8');
  if(env.template_id==='T02')$('#file-notice').textContent=tr('release.relative');
  if(Object.hasOwn(data,'pending_upload'))directUploader.reconcile(env.environment_id,data.pending_upload?.upload_id);
  $('#file-notice').textContent=env.template_id==='T07'?tr("ui.d951fe9b8cf0"):tr("ui.df347cf7aca4",{p0:(data.limits?.max_files||32),p1:((data.limits?.max_file_bytes||8192)/1024),p2:((data.limits?.max_total_bytes||262144)/1024)});
  $('#file-list').replaceChildren(element('p',tr("ui.33eda82d0811",{p0:data.writes_used??tr('common.unknown'),p1:data.limits.max_writes??tr('common.unknown')})));
  for(const file of data.items){
    const row=element('p');
    row.append(element('span',file.key+' · '+file.size+' byte'));
    if(env.template_id==='T07')row.append(button(tr("ui.9ee5e6905c7d"),async()=>{
      const share=await post('/environments/'+env.environment_id+'/share',{key:file.key});
      const a=element('a',tr("ui.1eea0b82634b")+timestamp(share.expires_at));a.href=share.url;a.target='_blank';a.rel='noopener noreferrer';row.append(a);notice(share.notice);
    }));
    else if(!data.draft_release_id){const a=element('a',tr("ui.c36c4e9efc99"));a.href=env.access_address+(data.public_content_base||(env.template_id==='T06'?'/files/':'/'))+file.key.split('/').map(encodeURIComponent).join('/');a.target='_blank';a.rel='noopener noreferrer';row.append(a);}
    $('#file-list').append(row);
  }
  const old=$('#file-release-controls');if(old)old.remove();
  const controls=element('div');controls.id='file-release-controls';
  if(env.template_id==='T02')renderReleaseStudio(controls,data);
  const progress=element('p');progress.id='file-progress';progress.setAttribute('aria-live','polite');controls.append(progress);
  controls.append(element('p',tr('upload.limits',{files:data.limits.max_files,size:data.direct_upload_enabled?data.limits.max_file_bytes:Math.min(data.legacy_inline_max_file_bytes||8192,data.limits.max_file_bytes),total:data.limits.max_total_bytes})));
  if(data.pending_upload)progress.textContent=tr('upload.pending',{key:data.pending_upload.key});
  if(data.pending_upload&&(data.direct_upload_enabled||data.pending_upload.can_cancel))controls.append(button(tr('upload.cancel'),async()=>{const result=await directUploader.cancel(env.environment_id,data.pending_upload.upload_id);if(result?.operation_id){track(result);$('#files-dialog').close();await refresh();}else{ $('#file-progress').textContent=tr('upload.cancelled');await openFiles(env);}}));
  if(data.direct_upload_enabled&&env.template_id==='T02'){
    controls.append(element('p',tr('release.explanation')),element('p',tr('release.relative')));
    if(!data.draft_release_id)controls.append(button(tr('release.prepare'),async()=>{await mutate('/environments/'+env.environment_id+'/releases',{});await openFiles(env);}));
    if(data.draft_release_id)controls.append(button(tr('release.activate'),async()=>{if(!confirm(tr('release.confirm')))return;track(await mutate('/environments/'+env.environment_id+'/releases/activate',{release_id:data.draft_release_id,confirmed:true}));$('#files-dialog').close();await refresh();}));
    if(data.previous_release_id)controls.append(button(tr('release.rollback'),async()=>{if(!confirm(tr('release.confirm')))return;track(await mutate('/environments/'+env.environment_id+'/releases/activate',{release_id:data.previous_release_id,confirmed:true}));$('#files-dialog').close();await refresh();}));
  }
  $('#file-form').prepend(controls);$('#file-form').reset();$('#file-input').required=true;if(data.pending_upload)$('#file-key').value=data.pending_upload.key;$('#file-submit').disabled=data.write_enabled===false||!!data.pending_upload&&!data.direct_upload_enabled;if(!$('#files-dialog').open)$('#files-dialog').showModal();
}
async function submitFile(ev){
  ev.preventDefault();
  if(fileBusy)return;
  const file=selectedDroppedFile||$('#file-input').files[0];
  if(!file||!fileEnvironment)return;
  const maximum=fileListing?.direct_upload_enabled?Number(fileListing.limits.max_file_bytes):Math.min(Number(fileListing?.legacy_inline_max_file_bytes||8192),Number(fileListing?.limits?.max_file_bytes||8192));
  if(file.size>maximum)throw Error(tr('upload.limit',{size:maximum}));
  const extension=file.name.split('.').pop().toLowerCase();
  const types={html:'text/html',htm:'text/html',css:'text/css',js:'application/javascript',json:'application/json',txt:'text/plain',png:'image/png',jpg:'image/jpeg',jpeg:'image/jpeg',svg:'image/svg+xml',pdf:'application/pdf',zip:'application/zip',csv:'text/csv',webp:'image/webp'};
  const type=types[extension];
  if(!type)throw Error(tr("ui.5384d6802927"));
  if(fileListing?.direct_upload_enabled){
    const key=$('#file-key').value;let expectedVersion;
    if(fileListing.items.some(item=>item.key===key)){
      if(!confirm(tr('upload.replace',{key})))return;
      expectedVersion=(await post('/environments/'+fileEnvironment.environment_id+'/files/metadata',{key})).version_id;
    }
    $('#file-submit').disabled=true;fileBusy=true;
    try{const op=await directUploader({environment:fileEnvironment.environment_id,file,key,contentType:type,releaseId:fileListing.draft_release_id,expectedVersion,onProgress:p=>{$('#file-progress').textContent=tr('upload.progress',{percent:p??'…'});}});track(op);$('#files-dialog').close();await refresh();}
    finally{fileBusy=false;$('#file-submit').disabled=fileListing?.write_enabled===false;}return;
  }
  const bytes=new Uint8Array(await file.arrayBuffer());
  const body={key:$('#file-key').value,content_base64:btoa(String.fromCharCode(...bytes)),content_type:type};
  const scope=fileEnvironment.environment_id+'/files/'+JSON.stringify(body);
  $('#file-submit').disabled=true;fileBusy=true;
  try{
    const op=await post('/environments/'+fileEnvironment.environment_id+'/files',body,idempotency(scope));
    commands.delete(scope);track(op);$('#files-dialog').close();await refresh();
  }finally{fileBusy=false;$('#file-submit').disabled=fileListing?.write_enabled===false;}
}
async function openRecords(env){recordEnvironment=env;recordOperation=null;$('#record-form').reset();$('#record-notice').textContent=tr('ui.fe3e135652ef');$('#record-submit').textContent=tr('ui.c179be6e3bda');$('#record-result').replaceChildren(element('p',tr('experience.dataHint')));setRecordBusy(false);$('#records-dialog').showModal();}
function setRecordBusy(busy){for(const id of ['record-submit','record-read','record-id','record-text'])$('#'+id).disabled=busy;}
function updateRecordOperation(){
  if(!recordEnvironment||!recordOperation||!$('#records-dialog').open)return;
  const op=operations.get(recordOperation);if(!op||op.environment_id!==recordEnvironment.environment_id)return;
  const done=['SUCCEEDED','FAILED','CANCELLED'].includes(op.status);setRecordBusy(recordSubmitting||!done);
  $('#record-notice').textContent=operationPresentation(op).title+' · '+operationPresentation(op).phase;
  if(op.status==='SUCCEEDED')renderRecordResult($('#record-result'),op.result);
  if(op.status==='FAILED')$('#record-notice').textContent=errorText({code:String(op.error?.code||op.error||'FAILED').split(':')[0]});
}
async function recordCommand(action,body={}){
 if(recordSubmitting||!recordEnvironment)return;const env=recordEnvironment;
 const pending=recordOperation&&operations.get(recordOperation);if(pending&&!['SUCCEEDED','FAILED','CANCELLED'].includes(pending.status))return;
 const eid=env.environment_id,scope=eid+'/'+action+'/'+JSON.stringify(body);recordSubmitting=true;setRecordBusy(true);$('#record-notice').textContent=tr('experience.dataPending');
 try{const op=await post('/environments/'+eid+'/'+action,body,idempotency(scope));track(op);commands.delete(scope);if(recordEnvironment===env){recordOperation=op.operation_id;updateRecordOperation();}await refresh();}
 catch(error){if(recordEnvironment===env)$('#record-notice').textContent=error.message;throw error;}
 finally{recordSubmitting=false;if(recordEnvironment===env){setRecordBusy(false);updateRecordOperation();}}
}
$('#record-form').onsubmit=ev=>{ev.preventDefault();const body={record_id:$('#record-id').value,text:$('#record-text').value};if(new TextEncoder().encode(body.text).length>256)return notice(tr("ui.8190853f54a1"));recordCommand(recordEnvironment.template_id==='T10'?'load_dataset':'put_record',body).catch(showError);};
$('#record-read').onclick=()=>recordCommand(recordEnvironment.template_id==='T10'?'query_demo':'list_records').catch(showError);
$('#record-close').onclick=()=>$('#records-dialog').close();
$('#file-form').onsubmit=ev=>submitFile(ev).catch(error=>{$('#file-notice').textContent=error.message;showError(error);});
$('#file-close').onclick=()=>$('#files-dialog').close();
$('#file-input').onchange=()=>{selectedDroppedFile=null;const file=$('#file-input').files[0];if(file){$('#file-key').value=file.name;$('#file-selection').textContent=file.name;}};
createFileDropZone({zone:$('#file-dropzone'),input:$('#file-input'),allowed:()=>!fileBusy&&fileListing?.write_enabled!==false&&!fileListing?.pending_upload,onError:message=>$('#file-notice').textContent=message,onSelect:file=>{selectedDroppedFile=file;$('#file-input').required=false;$('#file-selection').textContent=file.name;$('#file-key').value=file.name;}});
$('#ssh-close').onclick=()=>$('#ssh-dialog').close();
$('#ssh-copy').onclick=async()=>{try{await navigator.clipboard.writeText($('#ssh-command').value);$('#ssh-notice').textContent=tr('experience.copied');}catch{$('#ssh-command').focus();$('#ssh-command').select();$('#ssh-notice').textContent=tr('experience.copyFallback');}};
const authentication=createCognitoAuth({cfg,onSignup:email=>registration.open(email),onUnconfirmed:email=>registration.openVerification(email),onAuthenticated:async(tokens,options)=>{
  const saved=session.accept(tokens,{method:'api',remember:options?.remember!==false});await start();
  if(options?.remember!==false&&!saved.remembered)notice(tr('session.storageUnavailable'));
}});
const registration=createRegistration({cfg,onSignin:email=>authentication.open(email),onConfirmed:email=>{notice(tr("ui.0c6c1d325d84"));authentication.open(email);}});
$('#signup').onclick=()=>{try{registration.open();}catch(error){showError(error);}};
$('#login').onclick=()=>login().catch(showError);$('#logout').onclick=()=>logout().catch(showError);$('#refresh').onclick=()=>refresh().catch(showError);
if($('#quota-signin'))$('#quota-signin').onclick=()=>login().catch(showError);
async function start(){await callback();
  if(session.hasSession()){
    notice(tr('session.restoring'));
    try{await ensureToken();}
    catch(error){
      if(session.hasSession()){
        accessToken=null;renderShell();renderCatalog(templatePreviews,{guest:true});notice(tr('session.retry'));
        $('#notice').append(button(tr('session.retryButton'),()=>start().catch(showError)));return;
      }
    }
  }
$('#login').hidden=!!accessToken;$('#signup').hidden=!!accessToken;$('#logout').hidden=!accessToken;if(!accessToken)await loadCatalog();if(!cfg.configured){notice(tr("ui.385b628c4508"));return;}if(!accessToken){notice(tr("ui.f7bd3ba97449"));return;}const account=await api('/account');await languageReady;await accountLanguage(account,language=>api('/account/preferences',{method:'PUT',body:JSON.stringify({language})}));emailVerified=account.email_verified===true;if(!emailVerified){notice(tr("ui.36b45c9ead3c"));$('#account-settings').hidden=false;return;}notice(tr("ui.2baa339efe6a"));await Promise.all([loadCatalog(),refresh()]);if(creation.restorePending())$('#create-dialog').showModal();if(portal.isAdmin())await portal.loadAdmin();
  // A recovered request takes precedence over guest navigation. Never auto-confirm a quote.
  if(pendingGuestTemplate){const template=catalogCache.get(pendingGuestTemplate);pendingGuestTemplate=null;if(template?.create_enabled&&!creation.snapshot().open)await openCreate(template);}
}
setInterval(async()=>{if(!accessToken||!emailVerified||document.hidden)return;try{for(const [id,op]of operations){if(!['SUCCEEDED','FAILED','CANCELLED'].includes(op.status))operations.set(id,await api(op.admin_actor&&portal.isAdmin()?'/admin/operations/'+id:'/operations/'+id));}renderOperations();await refresh();}catch(e){showError(e);}},10000);
async function mutate(path,body={}){const scope=path+'/'+JSON.stringify(body),result=await post(path,body,idempotency(scope));commands.delete(scope);return result;}
const costText=money;
let creationRenderKey='',creationStep=-1;
function renderCreation(state){const q=state.quote;
  const props={...state,title:state.recoveryPoint?tr("ui.78e1f5d1a151"):tr("ui.2a1c4f55bfcf")+templateText(state.template),description:descriptions[state.template?.template_id]||'',backupScope:backupScope(state.template),limitsText:$('#limits-summary').textContent,
    quoteRows:q?[[tr("ui.37994610d585")+q.estimate_hours+tr("ui.8a94bb173e0a"),q.preview.total_milliusd],[tr("ui.6025fbc799bb")+(q.operating_policy.period_minutes??q.estimate_hours*60)+tr("ui.cf728a6aa3dd"),q.first_period.total_milliusd],...(q.operating_policy.mode==='CONTINUOUS'?[]:[[tr("ui.f879ef3725af")+q.operating_policy.period_minutes+tr("ui.cf728a6aa3dd"),q.renewal_period.total_milliusd]]),[tr("ui.4874f12343d3")+q.after_shutdown.period_hours+tr("ui.9e4dcadbbda6"),q.after_shutdown.total_milliusd],[tr("ui.5194e281870d"),q.initial_commitment_milliusd]].map(([label,value])=>({label,value:costText(value)})):[],priceUpdatedAt:Number.isFinite(Date.parse(q?.first_period.price_updated_at))?date(Date.parse(q.first_period.price_updated_at)/1000):q?.first_period.price_updated_at||tr("ui.7352ab1e6414"),region:q?.first_period.region||tr("ui.7352ab1e6414"),assumptions:q?{first:q.first_period,renewal:q.renewal_period,after_shutdown:q.after_shutdown}:null,unknown:q?[...(q.quote_expires_at?[tr('quote.expires',{time:date(q.quote_expires_at)})]:[]),tr('cost.estimateOnly'),tr('cost.retained'),tr('cost.limitUnknown'),...(q.approved?[]:[tr('cost.pricesPending')])]:[],budgetScope:q?.operating_policy?.mode==='CONTINUOUS'?tr('continuous.explanation'):q?.budget_scope?tr('cost.budgetScope'):''};
  const key=JSON.stringify(props);if(key!==creationRenderKey){creationView.update(props);creationRenderKey=key;}
  if(state.step!==creationStep&&state.open&&$('#create-dialog').open){const field=$('#create-dialog').querySelector('fieldset:not([hidden]) input:not([disabled]),fieldset:not([hidden]) select:not([disabled])');if(field)field.focus();else{$('#create-step-title').setAttribute('tabindex','-1');$('#create-step-title').focus();}}
  creationStep=state.open?state.step:-1;
  if(!state.open&&$('#create-dialog').open)$('#create-dialog').close();
}
async function assessCreation(){
  const state=creation.snapshot();if(!state.open||state.busy||state.uncertain)return;
  $('#create-dialog').close();await recommendations.open({assess:true,fromCreation:true,templateId:state.template.template_id,region:state.form.region,profileId:state.form.configurationId,form:state.form,workload:state.planningWorkload});
}
const recommendations=createRecommendations({api,isAuthenticated:()=>!!accessToken&&emailVerified,login,onClose:({selected,context})=>{if(!selected&&context.fromCreation&&creation.snapshot().open)$('#create-dialog').showModal();},onSelect:async option=>{
  if(creation.snapshot().busy||creation.snapshot().uncertain)throw Error(tr('rec.creationBusy'));
  await loadCatalog();const template=catalogCache.get(option.template_id),policy=option.creation_defaults.operating_policy;
  if(!template||!creation.open(template,null,option.configuration,option.region))throw Error(tr('rec.selectionError'));
  creation.change({configurationId:option.profile_id,estimateHours:String(option.creation_defaults.estimate_hours),mode:policy.mode,periodMinutes:String(policy.period_minutes||60),endingPolicy:policy.ending_policy,budgetUsd:policy.budget_limit_milliusd==null?'':String(policy.budget_limit_milliusd/1000)});
  creation.setWorkload(option.creation_defaults.planning_workload);$('#create-dialog').showModal();
}});
if($('#recommend-config'))$('#recommend-config').onclick=()=>recommendations.open().catch(showError);
const creationView=createCreationView({onAssess:()=>assessCreation().catch(showError),onFieldChange:patch=>creation.change(patch),onNext:()=>creation.next().catch(showError),onBack:()=>creation.back(),onConsent:value=>creation.consent(value),onRetryQuote:()=>creation.loadQuote().catch(showError),onCancel:()=>creation.cancel(),onSubmit:()=>creation.submit().catch(showError)});
const creation=createCreationFlow({journal:createJournal({get storage(){try{return sessionStorage;}catch{return null;}},owner:()=>{const identity=session.identity();return identity?JSON.stringify([cfg.apiBase,identity.iss,identity.sub]):null;}}),estimate:body=>post('/estimates',body),create:(body,key)=>post('/environments',body,key),costAllowed:quote=>portal.costAllowed(quote),costError:quote=>portal.costError(quote),keyFor:idempotency,forgetKey:scope=>commands.delete(scope),onChange:renderCreation,onAccepted:async op=>{navigateSection('operations-section');track(op);try{await refresh();}catch(error){notice(tr("ui.5e23e04f8507")+op.operation_id+tr("ui.6420e2fb2719")+error.message+tr("ui.5f61e892fc4f"));}}});
$('#create-dialog').addEventListener('cancel',event=>{event.preventDefault();creation.cancel();});
const navigationItems=[['overview-snapshot',tr('workspace.overview')],['catalog-section',tr("ui.400a2cde4813")],['environments-section',tr("ui.e16f1ec37c00")],['backups-section',tr("ui.7c2cb2c2496d")],['operations-section',tr("ui.7588a692c49b")],['history-section',tr("ui.0a23570855ef")]].map(([id,label])=>({id,label}));
function navigateSection(id){if(!navigationItems.some(item=>item.id===id)&&!(id==='admin'&&portal.isAdmin()))return;const target=document.getElementById(id);if(!target||target.hidden)return;history.replaceState({},'','#'+id);renderShell();document.body.classList.remove('workspace-menu-open');if(document.getElementById('workspace-dashboard'))window.scrollTo?.({top:0,behavior:'instant'});else target.scrollIntoView?.({block:'start',behavior:'auto'});target.setAttribute('tabindex','-1');target.focus({preventScroll:true});document.getElementById('workspace-menu')?.setAttribute('aria-expanded','false');}
window.addEventListener('cloudhub:navigate',event=>navigateSection(event.detail));
const shellView=createShellView({onNavigate:navigateSection,onRefresh:()=>refresh().catch(showError)});
function renderShell(){const authenticated=!!accessToken&&emailVerified,admin=authenticated&&portal.isAdmin();
  for(const id of ['overview-snapshot','environments-section','backups-section','operations-section','history-section'])if($('#'+id))$('#'+id).hidden=!authenticated;
  document.body.dataset.session=authenticated?'signed-in':'guest';
  let workspaceView=location.hash.slice(1)||(authenticated?'overview-snapshot':'catalog-section');
  if(!authenticated&&workspaceView!=='catalog-section')workspaceView='catalog-section';
  if(![...navigationItems.map(x=>x.id),...(admin?['admin']:[])].includes(workspaceView))workspaceView=authenticated?'overview-snapshot':'catalog-section';
  document.body.dataset.workspaceView=workspaceView;
  const activeLabel=navigationItems.find(x=>x.id===workspaceView)?.label||tr('ui.249d6a3df931');
  if(document.getElementById('workspace-route-title'))document.getElementById('workspace-route-title').textContent=activeLabel;
  renderWorkspaceDashboard(document.getElementById('workspace-dashboard'),cachedEnvironments,{navigate:navigateSection,detail:env=>lifecycle.detail(env),authenticated,loading:overviewLoading,lastUpdated:overviewUpdated,onError:showError,choose:tid=>{const tpl=catalogCache.get(tid);if(tpl?.create_enabled)return openCreate(tpl);navigateSection('catalog-section');},help:()=>recommendations.open()});
  const catalog=$('#catalog-section'),envSection=$('#environments-section');if(catalog&&envSection){if(authenticated&&envSection.nextElementSibling!==catalog)catalog.before(envSection);else if(!authenticated&&catalog.nextElementSibling!==envSection)envSection.before(catalog);}
shellView.update({authenticated,admin,activeSection:workspaceView,loading:overviewLoading,error:overviewError,lastUpdatedText:overviewUpdated?timestamp(overviewUpdated):'',...(overviewUpdated?workspaceOverview(cachedEnvironments):{stats:[],estimateText:tr("ui.b6858ba2e3b7"),actualCostText:tr("ui.b6858ba2e3b7"),coverageText:tr("ui.229524c2fd91")}),navItems:authenticated?(admin?[...navigationItems,{id:'admin',label:tr("ui.249d6a3df931")}]:navigationItems):navigationItems.filter(x=>x.id==='catalog-section')});}
window.addEventListener('hashchange',()=>navigateSection(location.hash.slice(1)));
const lifecycle=createLifecycleUI({api,mutate,track,refresh,element,timestamp,notice});
const portal=createPortal({api,post,notice,element,button,timestamp,track,refresh,operations,renderOperations,cfg,onRenew:env=>lifecycle.openManagement(env,'renew'),onEnvironment:env=>lifecycle.detail(env),getToken:()=>accessToken,ensureToken,mutate,onEmailVerified:start,getApplicationOptions:env=>{const tpl=catalogCache.get(env.template_id),profile=tpl?.regions?.find(r=>r.region===env.region)?.configuration_options?.find(p=>Object.keys(p.configuration).length===Object.keys(env.configuration||{}).length&&Object.entries(p.configuration).every(([k,v])=>env.configuration[k]===v));return (tpl?.application_options?.[env.region]||[]).map(a=>({...a,enabled:a.enabled&&(!a.configuration_ids||a.configuration_ids.includes(profile?.id||'standard'))}));}});
for(const id of ['environment-search','environment-status','environment-template'])$('#'+id).addEventListener(id==='environment-search'?'input':'change',renderEnvironments);
renderShell();start().then(()=>{renderShell();if(location.hash)navigateSection(location.hash.slice(1));}).catch(error=>{showError(error);renderShell();});

async function readOwnedApi(env){
 if(recordSubmitting)return;await openRecords(env);recordSubmitting=true;setRecordBusy(true);$('#record-notice').textContent=tr('experience.dataPending');
 try{await ensureToken();const sentSession=session.id(),response=await fetch(env.access_address,{headers:{Authorization:'Bearer '+accessToken}}),value=await response.json();
  if(sentSession!==session.id()||recordEnvironment!==env)return;
  if(!response.ok)throw Error(tr('ui.1ce5067f3892')+response.status);
  renderRecordResult($('#record-result'),value);$('#record-notice').textContent=tr('experience.updated',{time:timestamp(Date.now()/1000)});
 }catch(error){if(recordEnvironment===env)$('#record-notice').textContent=error.message;throw error;}
 finally{recordSubmitting=false;if(recordEnvironment===env)setRecordBusy(false);}
}

async function ensureToken(){
  try{accessToken=await session.ensure();}
  catch(error){if(!session.hasSession()&&accessToken===null)signedOut();throw error;}
}

onLanguageChange(()=>{if(!accessToken){renderCatalog(templatePreviews,{guest:true});if(cfg.configured)notice(tr("ui.f7bd3ba97449"));}portal.renderLimits();renderShell();renderEnvironments();renderOperations();if(creation.snapshot().open)renderCreation(creation.snapshot());portal.renderHistory(cachedEnvironments);});

if(typeof ResizeObserver!=='undefined'){new ResizeObserver(entries=>{document.documentElement.style.setProperty('--cloudhub-topbar-clearance',(Math.ceil(entries[0].target.getBoundingClientRect().height)+56)+'px');}).observe(document.querySelector('.app-topbar'));}

// UI clock is independent of API polling; background tabs never refresh quotes.
setInterval(()=>{if(document.hidden)return;updateClocks();const state=creation.snapshot();if(state.open){creationView.tick?.(state);Promise.resolve(creation.reconcile({refresh:true})).catch(showError);}},1000);
document.addEventListener('visibilitychange',()=>{if(!document.hidden){updateClocks();Promise.resolve(creation.reconcile({refresh:true})).catch(showError);}});

window.addEventListener('cloudhub:detail',event=>{if(accessToken&&emailVerified&&cachedEnvironments.some(env=>env.environment_id===event.detail.environment_id))renderWorkspaceDetailTools(event.detail,{openFiles,openRecords,downloadKey,navigate:navigateSection,onError:showError});});

function workspaceOverview(items){const model=environmentOverview(items),groups=[['READY'],['PROVISIONING','BACKING_UP','RETIRING','PAUSING','RESTARTING'],['PAUSED'],['CREATE_FAILED','ERROR_RETAINED','RESIDUAL']];return {...model,stats:model.stats.map((stat,index)=>({...stat,count:items.filter(env=>groups[index].includes(env.status)).length}))};}

function environmentConfigurationLabel(env){const tpl=catalogCache.get(env.template_id),profiles=tpl?.regions?.find(row=>row.region===env.region)?.configuration_options||tpl?.configuration_options||[];const profile=profiles.find(row=>Object.entries(row.configuration).every(([key,value])=>env.configuration?.[key]===value));return profile?profileLabel(env,profile):null;}
