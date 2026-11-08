import {t,number,money} from './i18n.js';
import {appendEnvironmentClock} from './cockpit.js';
const known=value=>value!==null&&value!==undefined&&value!==''&&Number.isFinite(Number(value))&&Number(value)>=0;
const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
export function budgetDecision(limits,quote){
 if(!limits)return {allowed:false,message:t('wallet.loading')};
 if(!quote?.approved||quote.budget_feasible===false||!known(quote.total_milliusd))return {allowed:false,message:t('wallet.prices')};
 const required=Number(quote.total_milliusd),balance=limits.wallet?.balance_milliusd??limits.user_remaining_milliusd??limits.remaining_milliusd;
 if(!known(balance))return {allowed:false,message:t('wallet.loading')};
 if(Number(balance)<required)return {allowed:false,scope:'ACCOUNT_WALLET',message:t('wallet.insufficient',{balance:money(balance),required:money(required)})};
 const platform=limits.platform_budget?.remaining_milliusd??limits.global_remaining_milliusd??limits.remaining_milliusd;
 if(!known(platform))return {allowed:false,message:t('wallet.loading')};
 if(Number(platform)<required)return {allowed:false,scope:'PLATFORM',message:t('wallet.platformShort',{balance:money(balance),available:money(platform),required:money(required)})};
 if(!(limits.remaining_environments>0))return {allowed:false,scope:'ENVIRONMENT_QUOTA',message:t('wallet.environmentQuota')};
 return {allowed:true,message:''};
}
export function renderQuotaVisual(limits,{environments=[],onRenew}={}){
 const host=document.querySelector('#quota-visual');if(!host)return;
 const details=document.querySelector('#quota-explanation'),mode=limits?'account':'guest';
 if(details&&details.dataset.mode!==mode){details.open=false;details.dataset.mode=mode;}
 for(const id of ['quota-guest','quota-signin']){const n=document.getElementById(id);if(n)n.hidden=!!limits;}
 host.hidden=!limits;host.toggleAttribute('data-wallet',!!limits?.wallet);host.replaceChildren();if(!limits)return;
 function bar(label,value,maximum,text){
  const row=el('div',null,'quota-meter'),head=el('div',null,'quota-meter-heading');head.append(el('span',label),el('strong',text));row.append(head);
  if(known(value)&&known(maximum)&&Number(maximum)>0){const meter=el('div',null,'quota-track'),fill=el('span');const percentage=Math.min(100,Math.max(0,Number(value)/Number(maximum)*100));
   meter.setAttribute('role','progressbar');meter.setAttribute('aria-label',label);meter.setAttribute('aria-valuemin','0');meter.setAttribute('aria-valuemax',String(maximum));meter.setAttribute('aria-valuenow',String(Math.min(Number(value),Number(maximum))));meter.setAttribute('aria-valuetext',text);fill.style.width=percentage+'%';meter.append(fill);row.append(meter);}
  host.append(row);
 }
 const active=limits.active,max=limits.max_active,wallet=limits.wallet,remaining=wallet?.balance_milliusd??limits.remaining_milliusd,budget=limits.user_budget_milliusd;
 if(wallet)host.append(el('strong',t('wallet.title')));
 bar(t('redesign.active'),active,max,known(active)&&known(max)?number(active)+' / '+number(max):t('common.unknown'));
 bar(t(wallet?'wallet.available':'experience.forecastAvailable'),remaining,budget,known(remaining)?money(remaining):t('common.unknown'));
 if(known(budget))host.append(el('small',t(wallet?'wallet.granted':'redesign.accountCap',{amount:money(budget)}),'quota-cap-note'));
 if(wallet)host.append(el('small',t('wallet.committed',{amount:money(wallet.committed_milliusd)}),'quota-cap-note'));
 const forecast=limits.forecast;
 if(forecast)host.append(el('small',t(wallet?'wallet.ledgerSummary':'ledger.summary',{future:money(forecast.future_reserved_milliusd),accrued:money(forecast.accrued_estimate_milliusd),legacy:money(forecast.legacy_unallocated_milliusd)}),'quota-cap-note'));
 if(wallet&&known(limits.global_remaining_milliusd))host.append(el('small',t('wallet.platformAvailable',{amount:money(limits.global_remaining_milliusd)}),'quota-cap-note'));
 if(wallet)host.append(el('small',t('wallet.disclaimer'),'quota-cap-note'));
 const next=environments.filter(e=>e.status==='READY'&&e.operating_policy?.mode!=='CONTINUOUS'&&Number(e.deadline)>0).sort((a,b)=>Number(a.deadline)-Number(b.deadline))[0];
 if(next){const section=el('div',null,'quota-next-action');section.append(el('small',next.template_id+' · '+next.environment_id));appendEnvironmentClock(section,next);
  if(onRenew){const renew=el('button',t('experience.reviewRenew'),'btn btn-secondary');renew.type='button';renew.disabled=!!next.lock||!!next.schedule_pending;renew.addEventListener('click',()=>Promise.resolve(onRenew(next)).catch(()=>{}));section.append(renew);}host.append(section);}
 host.append(el('small',t('redesign.quotaDisclaimer'),'quota-cap-note'));
}
