import {t,date,money,number,onLanguageChange} from './i18n.js';
import {errorText} from './error-text.js';

const titles={EXPIRY_SOON:'soon',RENEWAL_SUCCEEDED:'renewed',RENEWAL_BLOCKED:'blocked',RENEWAL_SYNC_PENDING:'pending',CONTINUOUS_BUDGET_WARNING:'budget',CONTINUOUS_COST_UNAVAILABLE:'prices'};
const reasons={BUDGET_EXCEEDED:'reasonBudget',CUMULATIVE_BUDGET_EXCEEDED:'reasonCumulative',QUOTA_EXCEEDED:'reasonQuota',PRICES_UNAPPROVED:'reasonPrices'};
const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
const button=(label,action)=>{const b=node('button',label,'btn btn-secondary');b.type='button';b.onclick=action;return b;};
export function createNotifications({api,mutate,getToken=()=>null,openEnvironment=()=>{},renew=()=>{}}){
 let epoch=0,request=0,prefRequest=0,active=false,showHistory=false,data={items:[],history:[],unread_count:0},prefs=null,dirty=false,lastRender='',busy=false;
 let bell=document.querySelector('#notification-bell');
 if(!bell){bell=node('button',undefined,'workspace-icon-button notification-bell');bell.type='button';bell.id='notification-bell';bell.hidden=true;document.querySelector('.topbar-actions')?.prepend(bell);}
 bell.setAttribute('aria-haspopup','dialog');bell.setAttribute('aria-controls','notification-dialog');
 const icon=document.createElementNS('http://www.w3.org/2000/svg','svg');icon.setAttribute('viewBox','0 0 24 24');icon.setAttribute('width','20');icon.setAttribute('height','20');icon.setAttribute('fill','none');icon.setAttribute('stroke','currentColor');icon.setAttribute('stroke-width','1.8');icon.setAttribute('aria-hidden','true');
 const path=document.createElementNS(icon.namespaceURI,'path');path.setAttribute('d','M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4');icon.append(path);
 const badge=node('span','0','notification-badge');badge.id='notification-unread';badge.setAttribute('aria-hidden','true');bell.replaceChildren(icon,badge);
 let dialog=document.querySelector('#notification-dialog');
 if(!dialog){dialog=node('dialog');dialog.id='notification-dialog';document.body.append(dialog);}
 dialog.classList.add('notification-dialog');dialog.setAttribute('aria-labelledby','notification-title');
 const heading=node('h2');heading.id='notification-title';const close=button('',()=>dialog.close());close.id='notification-close';close.classList.add('workspace-dialog-close');
 const head=node('div',undefined,'notification-heading');head.append(heading,close);
 const status=node('p');status.id='notification-status';status.setAttribute('role','status');
 const tab=button('',()=>{showHistory=!showHistory;lastRender='';render();});tab.id='notification-history';
 const list=node('div',undefined,'notification-list');list.id='notification-list';
 const settings=node('details',undefined,'notification-settings'),summary=node('summary'),hint=node('p'),form=node('form');form.id='notification-preferences';
 const inputs={};for(const key of ['email_enabled','expiry_email','renewal_email','maintenance_email']){const label=node('label',undefined,'notification-option'),input=node('input');input.type='checkbox';input.id='notification-'+key;input.name=key;const caption=node('span');label.append(input,caption);form.append(label);inputs[key]={input,caption};}
 const emailStatus=node('p');emailStatus.id='notification-email-status';emailStatus.setAttribute('role','status');
 const save=node('button',undefined,'btn btn-primary');save.type='submit';save.id='notification-save';
 const check=button('',()=>loadPreferences(true));check.id='notification-check';
 const disclaimer=node('p',undefined,'notification-disclaimer');form.append(save,check);settings.append(summary,hint,emailStatus,form,disclaimer);
 dialog.replaceChildren(head,status,tab,list,settings);
 const displayError=error=>{status.textContent=String(error?.code||'').startsWith('NOTIFICATION_')?t('notifications.emailError')+' ('+error.code+')':errorText(error);};
 const authenticated=()=>active&&!!getToken();
 function labels(){heading.textContent=t('notifications.title');close.textContent=t('notifications.close');summary.textContent=t('notifications.settings');hint.textContent=t('notifications.consent');disclaimer.textContent=t('notifications.disclaimer');
  for(const [key,field] of Object.entries(inputs))field.caption.textContent=t('notifications.'+key);
  save.textContent=t('notifications.save');check.textContent=t('notifications.check');tab.textContent=t(showHistory?'notifications.current':'notifications.history');tab.setAttribute('aria-pressed',String(showHistory));
  const count=Number(data.unread_count||0);bell.setAttribute('aria-label',t('notifications.bell',{count:number(count)}));badge.textContent=count>99?'99+':number(count);badge.hidden=count===0;
 }
 async function view(item,wantsRenew=false){
  const generation=epoch;status.textContent='';try{const env=await api('/environments/'+encodeURIComponent(item.environment_id));if(generation!==epoch||!authenticated())return;
   dialog.close();if(wantsRenew&&env.status==='READY'&&!env.lock&&env.deadline>Date.now()/1000)await renew(env);else await openEnvironment(env);
  }catch(error){if(generation===epoch&&authenticated())displayError(error);}
 }
 async function mark(item,control){const generation=epoch;control.disabled=true;try{await mutate('/notifications/'+encodeURIComponent(item.notification_id)+'/read',{});if(generation===epoch)await refresh();}catch(error){if(generation===epoch)displayError(error);}finally{if(generation===epoch)control.disabled=false;}}
 function render(){labels();const items=showHistory?(data.history||data.items||[]):(data.items||[]),stamp=JSON.stringify([items,showHistory]);if(stamp===lastRender)return;lastRender=stamp;list.replaceChildren();
  if(!items.length){list.append(node('p',t('notifications.empty'),'empty-state-message'));return;}
  for(const item of items){const card=node('article',undefined,'notification-card'+(!item.read_at&&item.current!==false?' is-unread':''));card.dataset.notificationId=item.notification_id;
   const maintenance=item.type==='MAINTENANCE_NOTICE';
   card.append(node('h3',maintenance?item.title:t('notifications.'+(titles[item.type]||'title'))),node('small',date(item.created_at)));
   if(maintenance){card.append(node('p',t('maintenance.kind.'+item.notice_kind)),node('p',item.message),node('p',t('maintenance.field.impact')+': '+item.impact),node('p',date(item.starts_at)+' → '+date(item.ends_at)),node('small',t('maintenance.noInfra')));}
   else card.append(node('p',String(item.environment_id||'')+' · '+String(item.region||''),'notification-meta'));
   if(item.type==='EXPIRY_SOON')card.append(node('p',t(item.mode==='AUTO_RENEW'?'notifications.autoSoon':'notifications.offSoon')));
   if(item.type==='CONTINUOUS_BUDGET_WARNING'||item.type==='CONTINUOUS_COST_UNAVAILABLE')card.append(node('p',t(item.type==='CONTINUOUS_BUDGET_WARNING'?'continuous.budgetWarning':'continuous.pricesUnavailable')));
   if(item.deadline)card.append(node('p',t('notifications.deadline')+': '+date(item.deadline)));
   if(item.current===false)card.append(node('p',t('notifications.superseded'),'notification-muted'));
   if(['RENEWAL_SUCCEEDED','RENEWAL_SYNC_PENDING'].includes(item.type))card.append(node('p',t('notifications.periodCost')+': '+money(item.period_estimate_milliusd)),node('p',t('notifications.cumulative')+': '+money(item.cumulative_milliusd)));
   if(item.type==='EXPIRY_SOON'&&item.mode==='AUTO_RENEW')card.append(node('p',t('notifications.periodCost')+': '+money(item.period_estimate_milliusd)),node('p',t('notifications.cumulative')+': '+money(item.cumulative_milliusd)),node('small',t('notifications.referenceEstimate')));
   if(item.type==='EXPIRY_SOON'||item.type==='RENEWAL_BLOCKED')card.append(node('p',t('notifications.ending')+': '+t(item.ending_policy==='PAUSE'?'notifications.pause':'notifications.retire')));
   if(item.code)card.append(node('p',reasons[item.code]?t('notifications.'+reasons[item.code]):errorText({code:item.code})),node('small',t('notifications.reason')+': '+String(item.code)));
   if(item.operation_id)card.append(node('small',t('notifications.support')+': '+String(item.operation_id)));
   if(item.email_status&&item.email_status!=='NOT_REQUESTED')card.append(node('small',t('notifications.emailState')+': '+t('notifications.status.'+item.email_status)));
   const actions=node('div',undefined,'notification-actions');if(maintenance){const link=node('a',t('maintenance.view'),'btn btn-secondary');link.href='/maintenance.html';actions.append(link);}else actions.append(button(t('notifications.view'),()=>view(item)));
   if(item.type==='EXPIRY_SOON'&&item.current!==false)actions.append(button(t('notifications.reviewRenew'),()=>view(item,true)));
   if(!item.read_at){const read=button(t('notifications.markRead'),()=>mark(item,read));actions.append(read);}
   card.append(actions);list.append(card);
  }
  if(data.truncated)list.append(node('p',t('notifications.truncated')));
 }
 function renderPreferences(){if(!prefs)return;labels();if(!dirty)for(const [key,field] of Object.entries(inputs))field.input.checked=!!prefs[key];
  inputs.email_enabled.input.disabled=!prefs.email_available;check.disabled=!prefs.email_available||!prefs.email_enabled||busy;save.disabled=busy;
  emailStatus.textContent=(prefs.masked_email?prefs.masked_email+' · ':'')+t(prefs.email_available?'notifications.status.'+prefs.email_status:'notifications.unavailable');
 }
 async function loadPreferences(recheck=false){const generation=epoch,sequence=++prefRequest;check.disabled=true;try{const result=recheck?await mutate('/account/notification-preferences/check',{}):await api('/account/notification-preferences');
   if(generation!==epoch||sequence!==prefRequest||!authenticated())return;prefs=result;renderPreferences();
  }catch(error){if(generation===epoch&&authenticated())displayError(error);}finally{if(generation===epoch)check.disabled=busy||!prefs?.email_available||!prefs?.email_enabled;}
 }
 settings.addEventListener('toggle',()=>{if(settings.open&&authenticated()&&!prefs)loadPreferences();});
 form.addEventListener('change',()=>{dirty=true;});
 form.onsubmit=async event=>{event.preventDefault();if(busy||!authenticated())return;const generation=epoch;busy=true;save.disabled=true;status.textContent='';
  try{const body=Object.fromEntries(Object.entries(inputs).map(([key,value])=>[key,value.input.checked]));const result=await mutate('/account/notification-preferences',body);
   if(generation!==epoch||!authenticated())return;prefs=result;dirty=false;renderPreferences();
  }catch(error){if(generation===epoch&&authenticated())displayError(error);}finally{if(generation===epoch){busy=false;renderPreferences();}}
 };
 async function refresh(){const generation=epoch,sequence=++request,token=getToken();if(!token){reset();return;}
  const result=await api('/notifications?schema=2');if(generation!==epoch||sequence!==request||getToken()!==token)return;
  active=true;bell.hidden=false;data=result||{items:[],history:[],unread_count:0};if(data.unread_count==null)data.unread_count=(data.items||[]).filter(x=>!x.read_at).length;render();
 }
 bell.onclick=()=>{if(!authenticated())return;status.textContent='';dialog.showModal();refresh().catch(displayError);};
 function reset(){epoch++;request++;prefRequest++;active=false;data={items:[],history:[],unread_count:0};prefs=null;dirty=false;busy=false;lastRender='';showHistory=false;list.replaceChildren();status.textContent='';emailStatus.textContent='';form.reset?.();for(const field of Object.values(inputs))field.input.checked=false;settings.open=false;bell.hidden=true;badge.hidden=true;if(dialog.open)dialog.close();}
 const stopLanguage=onLanguageChange(()=>{lastRender='';if(active){render();renderPreferences();}});
 reset();return {refresh,reset,dispose(){reset();stopLanguage();}};
}
