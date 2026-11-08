import {t,date,languages,languageState,onLanguageChange} from './i18n.js';
import {errorText} from './error-text.js';
const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
const btn=(key,fn)=>{const b=el('button',t(key),'btn btn-secondary');b.type='button';b.onclick=fn;return b;};
// Retain the command key after network errors; preview never confirms publication.
export function commandSession(api){const keys=new Map();return {reset(){keys.clear();},async send(path,body,method='POST'){
 const scope=method+' '+path+' '+JSON.stringify(body);if(!keys.has(scope))keys.set(scope,crypto.randomUUID());
 const result=await api(path,{method,body:JSON.stringify(body),headers:{'Idempotency-Key':keys.get(scope)}});keys.delete(scope);return result;
}};}
export function createAnnouncements({api,isAdmin}){
 let epoch=0,request=0,data={items:[]},draft=null,preview=null,busy=false,openedEpoch=0;
 const commands=commandSession(api),section=el('section',undefined,'maintenance-admin');section.id='admin-announcements';
 const heading=el('h3'),hint=el('p'),status=el('p'),list=el('div',undefined,'maintenance-list');status.setAttribute('role','status');
 const create=btn('maintenance.new',()=>open()),refreshButton=btn('maintenance.refresh',()=>refresh().catch(showError));section.append(heading,hint,create,refreshButton,status,list);document.querySelector('#admin')?.append(section);
 const dialog=el('dialog',undefined,'maintenance-editor'),form=el('form'),title=el('h2'),fields={},previewBox=el('section',undefined,'maintenance-preview');dialog.id='maintenance-editor';title.id='maintenance-editor-title';dialog.setAttribute('aria-labelledby',title.id);
 const fieldKeys=['title','message','impact','notice_kind','language','starts_at','ends_at'];
 for(const key of fieldKeys){const label=el('label'),caption=el('span'),input=el(key==='message'||key==='impact'?'textarea':['notice_kind','language'].includes(key)?'select':'input');input.id='maintenance-'+key;input.name=key;input.required=true;
  if(key==='title'){input.type='text';input.maxLength=120;}if(['message','impact'].includes(key)){input.rows=3;input.maxLength=key==='message'?2000:800;}
  if(key==='starts_at'||key==='ends_at')input.type='datetime-local';
  if(key==='language')for(const [code,name]of Object.entries(languages)){const option=el('option',name);option.value=code;input.append(option);}
  if(key==='notice_kind')for(const code of ['SCHEDULED','EXTENDED','COMPLETED']){const option=el('option');option.value=code;input.append(option);}
  label.append(caption,input);form.append(label);fields[key]={input,caption};
 }
 const timeHint=el('p'),emailLabel=el('label'),email=el('input'),emailCaption=el('span');email.type='checkbox';email.id='maintenance-send-email';emailLabel.append(email,emailCaption);
 const warning=el('p'),message=el('p');message.setAttribute('role','status');message.id='maintenance-editor-status';
 const save=btn('maintenance.save',()=>saveDraft()),review=btn('maintenance.preview',()=>reviewDraft()),publish=btn('maintenance.publish',()=>publishDraft()),close=btn('maintenance.close',()=>dialog.close());
 form.prepend(title);form.append(timeHint,emailLabel,warning,previewBox,message,save,review,publish,close);form.onsubmit=e=>e.preventDefault();dialog.append(form);document.body.append(dialog);
 function labels(){heading.textContent=t('maintenance.adminTitle');hint.textContent=t('maintenance.noInfra');create.textContent=t('maintenance.new');refreshButton.textContent=t('maintenance.refresh');title.textContent=t(draft?'maintenance.edit':'maintenance.new');
  for(const key of fieldKeys)fields[key].caption.textContent=t('maintenance.field.'+key);
  for(const option of fields.notice_kind.input.options)option.textContent=t('maintenance.kind.'+option.value);
  for(const [button,key]of [[save,'save'],[review,'preview'],[publish,'publish'],[close,'close']])button.textContent=t('maintenance.'+key);
  timeHint.textContent=t('maintenance.inputTimezone',{zone:Intl.DateTimeFormat().resolvedOptions().timeZone});emailCaption.textContent=t('maintenance.emailOptIn');warning.textContent=t('maintenance.confirmNotice');
 }
 function showError(error){status.textContent=errorText(error);}
 function render(){labels();list.replaceChildren();if(!data.items.length)list.append(el('p',t('maintenance.noDrafts')));
  if(!data.publication_enabled)status.textContent=t('maintenance.disabled');else if(status.textContent===t('maintenance.disabled'))status.textContent='';
  for(const item of data.items){const card=el('article',undefined,'card');card.append(el('h4',item.title),el('p',t('maintenance.status.'+item.status)),el('p',date(item.starts_at)+' → '+date(item.ends_at)),el('small',item.operation_id||item.announcement_id));
   if(item.public_status!=='SYNCED')card.append(el('p',t('maintenance.syncPending')+' · '+item.public_status));
   if(item.status==='DRAFT')card.append(btn('maintenance.edit',()=>open(item)));
   if(['DRAFT','QUEUED','PUBLISHED'].includes(item.status)&&(!item.published_at||item.current))card.append(btn('maintenance.withdraw',()=>withdraw(item)));
   if(item.public_status==='FAILED')card.append(btn('maintenance.retry',()=>run(()=>commands.send('/admin/announcements/'+item.announcement_id+'/retry',{expected_revision:item.revision}))));
   list.append(card);
  }
 }
 async function refresh(){if(!isAdmin())return;const generation=epoch,seq=++request;const result=await api('/admin/announcements');if(generation!==epoch||seq!==request||!isAdmin())return;data=result;render();}
 function reset(){epoch++;request++;data={items:[]};draft=null;preview=null;busy=false;commands.reset();list.replaceChildren();status.textContent='';previewBox.replaceChildren();form.reset?.();if(dialog.open)dialog.close();}
 const localDate=seconds=>{const d=new Date(seconds*1000);return new Date(d.getTime()-d.getTimezoneOffset()*60000).toISOString().slice(0,16);};
 function open(item){if(!isAdmin())return;openedEpoch=epoch;draft=item?{...item}:null;preview=null;previewBox.replaceChildren();message.textContent='';email.checked=false;
  const start=Math.ceil(Date.now()/60000)*60+3600,value=item||{title:'',message:'',impact:'',notice_kind:'SCHEDULED',language:languageState().locale,starts_at:start,ends_at:start+3600};
  for(const key of fieldKeys)fields[key].input.value=key.endsWith('_at')?localDate(value[key]):value[key];labels();updateButtons();dialog.showModal();
 }
 function updateButtons(){save.disabled=busy;review.disabled=busy;publish.disabled=busy||!preview||!data.publication_enabled;for(const field of Object.values(fields))field.input.disabled=busy;email.disabled=busy;}
 function invalidate(){preview=null;previewBox.replaceChildren();updateButtons();}
 form.addEventListener('input',invalidate);form.addEventListener('change',invalidate);
 function body(){if(!form.reportValidity())throw Error(t('maintenance.checkFields'));const result=Object.fromEntries(fieldKeys.map(key=>[key,key.endsWith('_at')?Math.floor(new Date(fields[key].input.value).getTime()/1000):fields[key].input.value]));if(result.ends_at<=result.starts_at)throw Error(t('maintenance.checkFields'));return result;}
 async function guard(fn){if(busy||!isAdmin())return;busy=true;updateButtons();message.textContent='';const generation=epoch;try{await fn();}catch(error){if(generation===epoch)message.textContent=errorText(error);}finally{if(generation===epoch){busy=false;updateButtons();}}}
 async function persist(){const payload=body(),result=await commands.send('/admin/announcements'+(draft?'/'+draft.announcement_id:''),draft?{...payload,expected_revision:draft.revision}:payload,draft?'PUT':'POST');if(openedEpoch!==epoch||!isAdmin())return null;draft=result;return result;}
 async function saveDraft(){await guard(async()=>{if(await persist()){invalidate();message.textContent=t('maintenance.saved');await refresh();}});}
 async function reviewDraft(){await guard(async()=>{const saved=await persist();if(!saved)return;const generation=epoch,result=await api('/admin/announcements/'+saved.announcement_id+'/preview',{method:'POST',body:JSON.stringify({expected_revision:saved.revision,send_email:email.checked})});if(generation!==epoch)return;preview=result;previewBox.replaceChildren(el('h3',saved.title),el('p',saved.message),el('p',saved.impact),el('p',date(saved.starts_at)+' → '+date(saved.ends_at)),el('p',t('maintenance.audience')),el('p',t('maintenance.emailCount',{count:result.confirmed_email_opt_ins||0})),el('p',t('maintenance.confirmNotice')));});}
 async function publishDraft(){await guard(async()=>{if(!preview||Date.now()/1000>=preview.expires_at){invalidate();throw Error(t('maintenance.previewExpired'));}if(!confirm(t('maintenance.confirmPublish')))return;const generation=epoch;await commands.send('/admin/announcements/'+draft.announcement_id+'/publish',{expected_revision:draft.revision,preview_id:preview.preview_id,confirm_publish:true});if(generation!==epoch)return;dialog.close();status.textContent=t('maintenance.syncPending');await refresh();});}
 async function run(fn){if(busy||!isAdmin())return;busy=true;const generation=epoch;try{await fn();if(generation===epoch)await refresh();}catch(error){if(generation===epoch)showError(error);}finally{if(generation===epoch)busy=false;}}
 async function withdraw(item){if(!confirm(t('maintenance.confirmWithdraw')))return;await run(()=>commands.send('/admin/announcements/'+item.announcement_id+'/cancel',{expected_revision:item.revision,confirm_cancel:true}));}
 onLanguageChange(()=>{render();if(dialog.open){invalidate();labels();}});labels();
 return {refresh,reset};
}
