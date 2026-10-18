import {t,money,date} from './i18n.js';
import {backupScope,profileLabel,regionLabel} from './catalog-text.js';
export function restoreReview(source){
 const rows=[t('detail.restore'),source.recovery_point+' · '+date(source.created_at),backupScope(source),regionLabel(source)+' — '+(source.region||t('common.unknown')),t('ui.87539be3fc65')+profileLabel(source,{configuration:source.configuration})];
 if(source.application?.release_id)rows.push(t('ux.app.version')+': '+source.application.release_id);
 return rows.join('\n');
}
const el=(tag,text)=>{const node=document.createElement(tag);if(text!=null)node.textContent=text;return node;};
const componentGroups={compute:'compute',web_compute:'compute',db_compute:'database',web_root:'storage',root:'storage',data:'storage',web_ipv4:'network',container:'compute',lambda_compute:'compute',lambda_requests:'requests',api:'requests',database:'database',db_storage:'storage',storage:'storage',root_storage:'storage',s3_storage:'storage',efs:'storage',backup:'backup',s3_backup:'backup',isolated_staging_storage:'staging',s3_requests:'requests',cloudfront_requests:'requests',viewer_function:'requests',transfer:'transfer',ipv4:'network',task_ipv4:'network',alb_ipv4:'network',load_balancer:'network',logs:'logs',control_plane:'management',management_reads:'management',secrets:'management',image_storage:'storage',restore_allowance:'backup'};
export const costComponent=key=>t('ux.cost.'+(componentGroups[key]||'other'));
export function appendCostSummary(host,cost){
 if(!cost)return;
 const table=el('dl');table.className='human-cost-lines';
 const grouped=new Map();for(const [key,value]of Object.entries(cost.lines||{})){if(value==null)continue;const label=costComponent(key);grouped.set(label,(grouped.get(label)||0)+Number(value));}
 for(const [label,value]of grouped)table.append(el('dt',label),el('dd',money(value*1000)));
 host.append(table,el('p',t('ux.cost.reserve')));
 if(cost.total_milliusd==null&&cost.known_subtotal_milliusd!=null)host.append(el('p',t('rec.knownSubtotal')+': '+money(Number(cost.known_subtotal_usd??cost.known_subtotal_milliusd/1000)*1000)));
 if(cost.assumptions?.cloudfront_price_class==='PriceClass_100')host.append(el('p',t('ux.priceClass')));
 if(cost.assumptions?.viewer_price_updated_at)host.append(el('p','CloudFront · '+t('rec.priceUpdated')+': '+date(Date.parse(cost.assumptions.viewer_price_updated_at)/1000)+' · '+cost.assumptions.viewer_price_version));
 host.append(el('p',t('ux.cost.coverage')));
}
export function missingDescription(code){
 if(code?.startsWith('price:cloudfront_viewer_'))return t('ux.missing.viewerPrice');
 return t(code?.startsWith('price:')?'ux.missing.price':'ux.missing.usage');
}
export function appendCleanupReport(host,report){
 const details=el('details');details.className='cleanup-report';details.append(el('summary',t('ux.cleanup.title')));
 details.append(el('p',t('ux.cleanup.scope')),el('p',t('ux.cleanup.checked')+': '+date(report.checked_at)));
 const table=el('table'),head=el('tr');for(const key of ['resource','result','reason','charge'])head.append(el('th',t('ux.cleanup.'+key)));const thead=el('thead');thead.append(head);table.append(thead);const body=el('tbody');table.append(body);
 const billable=new Set((report.billable||[]).map(x=>x.type+'|'+x.id));let count=0;
 for(const status of ['deleted','retained','residual','unknown','pending_deletion'])for(const item of report[status]||[]){
  count++;const row=el('tr');row.dataset.result=status;
  const charge=status==='deleted'?'none':status==='unknown'?'unknownCharge':billable.has(item.type+'|'+item.id)?'possible':status==='pending_deletion'&&item.billable===false?'none':'unknownCharge';
  row.append(el('td',item.type+' · '+item.id),el('td',t('ux.cleanup.'+status)),el('td',t('ux.cleanup.reason.'+status)+(item.retain_until?' · '+date(item.retain_until):'')),el('td',t('ux.cleanup.'+charge)));body.append(row);
 }
 if(!count)details.append(el('p',t('ux.cleanup.noEvidence')));
 details.append(table);
 const raw=el('details');raw.append(el('summary',t('rec.technical')),el('pre',JSON.stringify(report,null,2)));details.append(raw);host.append(details);return details;
}
export function backupStatus(status){
 const keys={AVAILABLE:'ui.f9950b8958fc',PENDING:'ui.e84898db736f',FAILED:'ui.710b8dc0a898',DELETED:'ui.412c1c534007',DELETING:'ui.07242e5e6f7d',DELETE_FAILED:'ui.75035719dd9a',EXPIRED:'ui.bd2b6fce2633',EXPIRING:'ui.4d76295e32c8'};
 return t(keys[status]||'common.unknown');
}
export function backupAvailability(rp,now=Date.now()){
 if(rp.action_availability)return rp.action_availability;
 const state=['DELETED','DELETING','PENDING','FAILED','EXPIRED','EXPIRING'].includes(rp.status)?rp.status:rp.status!=='AVAILABLE'&&rp.status!=='DELETE_FAILED'?'UNKNOWN':null;
 const busy=rp.in_use||rp.restore_lock||rp.export_lock||rp.delete_lock;
 const reason=busy?'BUSY':state||(Number(rp.retain_until)*1000<=now?'EXPIRED':rp.status==='DELETE_FAILED'?'DELETE_FAILED':null);
 return {restore:{allowed:!reason,reason},export:{allowed:!reason&&rp.status==='AVAILABLE',reason:reason||null},delete:{allowed:!busy&&!rp.retirement_protected&&['AVAILABLE','DELETE_FAILED'].includes(rp.status),reason:busy?'BUSY':rp.retirement_protected?'PROTECTED':state}};
}
export function explainDisabled(button,reason){if(button.disabled){const text=t('ux.backup.'+(reason||'UNKNOWN'));button.title=text;button.setAttribute('aria-label',button.textContent+' · '+text);}}
