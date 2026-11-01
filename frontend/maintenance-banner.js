import {t,date,onLanguageChange} from './i18n.js';
const el=(tag,text)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n;};
export function validateNotice(value){
 if(!value||value.schema!==1||value.publisher!=='cloudhub-maintenance'||!Number.isSafeInteger(value.generation)||value.generation<0||typeof value.active!=='boolean')throw Error('Invalid public notice');
 if(value.active){const a=value.announcement;if(!a||!['SCHEDULED','EXTENDED','COMPLETED'].includes(a.notice_kind)||!/^ann-[a-f0-9]{24}$/.test(a.announcement_id))throw Error('Invalid public notice');
  for(const [key,max]of [['title',120],['message',2000],['impact',800]])if(typeof a[key]!=='string'||!a[key].trim()||a[key].length>max)throw Error('Invalid public notice');
  if(!Number.isFinite(a.starts_at)||!Number.isFinite(a.ends_at)||a.ends_at<=a.starts_at)throw Error('Invalid public window');
 }return value;
}
export function noticePhase(a,now=Date.now()/1000){return a.notice_kind==='COMPLETED'?'completed':now<a.starts_at?'planned':now>a.ends_at?'overrun':'active';}
export function createPublicNotice({root,standalone=false,fetcher=fetch,now=()=>Date.now()/1000}){
 let value=null,request=0,stale=false;root.setAttribute('role','status');root.setAttribute('aria-live','polite');
 function render(){root.replaceChildren();root.hidden=!standalone&&!value?.active;if(root.hidden)return;
  if(!value?.active){root.append(el('h1',t(stale?'maintenance.unavailable':'maintenance.noActive')));return;}
  const a=value.announcement,title=el(standalone?'h1':'strong',a.title),message=el('p',a.message),impact=el('p',t('maintenance.field.impact')+': '+a.impact);title.lang=a.language;message.lang=a.language;impact.lang=a.language;
  root.append(el('span',t('maintenance.phase.'+noticePhase(a,now()))),title,message,el('p',t('maintenance.field.starts_at')+': '+date(a.starts_at)),el('p',t('maintenance.field.ends_at')+': '+date(a.ends_at)),impact,el('small',t('maintenance.noInfra')));
  if(stale)root.append(el('p',t('maintenance.stale')));if(!standalone){const link=el('a',t('maintenance.view'));link.href='/maintenance.html';root.append(link);}
 }
 async function refresh(){const seq=++request;try{const response=await fetcher('/maintenance.json',{cache:'no-store',credentials:'omit',signal:AbortSignal.timeout(5000)});if(!response.ok)throw Error('Notice unavailable');const raw=await response.text();if(raw.length>16384)throw Error('Notice too large');const next=validateNotice(JSON.parse(raw));if(seq!==request||value&&next.generation<value.generation)return;value=next;stale=false;render();}catch{if(seq!==request)return;stale=true;render();}}
 const off=onLanguageChange(render);render();return {refresh,dispose(){request++;off();},render};
}
const root=typeof document!=='undefined'&&document.querySelector('[data-maintenance-notice]');
if(root){const controller=createPublicNotice({root,standalone:root.hasAttribute('data-standalone')});controller.refresh();setInterval(()=>{if(!document.hidden)controller.refresh();},60000);}
