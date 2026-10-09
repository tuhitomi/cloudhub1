// Presentation only: actions delegate to the existing authenticated controllers.
import {t,money,languageState} from './i18n.js';
import {templateText,regionLabel} from './catalog-text.js';
import {templateIcon} from './catalog-view.js';
import {modeName,operatingPolicy} from './lifecycle.js';
import {appendEnvironmentClock} from './cockpit.js';

const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
const text=key=>t('workspace.'+key);
const statuses={READY:'ui.d654065d13f4',PAUSED:'ui.a919ce7fbdb6',PAUSING:'ui.e40cc1b782e8',RESTARTING:'ui.75f9ad677614',PROVISIONING:'ui.da7b559f5be4',BACKING_UP:'ui.ed47bc2df524',RETIRING:'ui.37488d76a81a',DELETED:'ui.412c1c534007',DELETING:'ui.07242e5e6f7d',DELETE_FAILED:'ui.75035719dd9a',RESIDUAL:'ui.58ba0d41d54f',ERROR_RETAINED:'ui.b4b193b11b9b',CREATE_FAILED:'ui.667c6ae33cc5'};
function badge(env){const n=el('span',t(statuses[env.status]||'common.unknown'),'status-pill');n.dataset.status=env.status;return n;}
function invoke(action,onError){return ()=>Promise.resolve().then(action).catch(onError);}
function svg(path){const n=el('span',null,'quick-icon');n.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="'+path+'"/></svg>';return n;}
function appLink(env){try{const u=new URL(env.access_address);if(!['http:','https:'].includes(u.protocol)||u.username||u.password)return null;const a=el('a',text('viewApp'),'btn btn-secondary');a.href=u.href;a.target='_blank';a.rel='noopener noreferrer';return a;}catch{return null;}}

export function renderWorkspaceDetailTools(env,{openFiles,openRecords,downloadKey,navigate,onError}){
 const dialog=document.querySelector('#environment-detail-dialog');dialog.querySelector('.workspace-detail-tools')?.remove();
 const host=el('div',null,'workspace-detail-tools'),identity=el('div',null,'workspace-detail-identity');identity.append(templateIcon(env.template_id),el('h3',templateText(env)),badge(env));host.append(identity,el('p',env.template_id+' · '+regionLabel(env)));
 const actions=el('div',null,'environment-primary-actions'),button=(label,action,disabled=false)=>{const b=el('button',label,'btn btn-secondary');b.type='button';b.disabled=disabled;b.onclick=invoke(()=>{dialog.close();return action();},onError);return b;};const unready=env.status!=='READY'||!!env.lock;
 const link=appLink(env);if(link)actions.append(link);
 if(['T02','T06','T07'].includes(env.template_id))actions.append(button(t('ui.67dd1d6fb247'),()=>openFiles(env),env.status!=='READY'||!!env.lock&&!String(env.lock).startsWith('upload-')));
 if(['T03','T04','T08','T09'].includes(env.template_id))actions.append(button(t('ui.0ce3732c6c81'),()=>openRecords(env),unready));
 if(['T01','T05'].includes(env.template_id))actions.append(button(t('ui.7b014eaf12f3'),()=>downloadKey(env.environment_id),unready));
 actions.append(button(text('viewBackups'),()=>navigate('backups-section')));host.append(actions);document.querySelector('#environment-detail').before(host);
}

export function renderWorkspaceDashboard(host,items,{navigate,detail,choose,help,authenticated=true,loading=false,lastUpdated=0,onError}){
 if(!host)return;
 if(!authenticated){host.replaceChildren();delete host.dataset.content;return;}
 const current=items.filter(env=>env.status!=='DELETED').slice().sort((a,b)=>Number(b.created_at||0)-Number(a.created_at||0));
 const key=JSON.stringify([languageState().locale,current,!!lastUpdated,!lastUpdated&&loading]);if(host.dataset.content===key)return;host.dataset.content=key;host.replaceChildren();
 const left=el('section',null,'dashboard-panel recent-panel'),head=el('div',null,'panel-header');
 head.append(el('h2',text('recent')));const more=el('button',text('allEnvironments')+' →','text-button');more.onclick=invoke(()=>navigate('environments-section'),onError);head.append(more);left.append(head);
 if(current.length){const list=el('div',null,'recent-list');for(const env of current.slice(0,4)){
  const row=el('button',null,'recent-row');row.type='button';row.append(templateIcon(env.template_id));const identity=el('span',null,'recent-identity');identity.append(el('strong',templateText(env)),el('small',env.template_id+' · '+regionLabel(env)));row.append(identity,badge(env),el('span','↗','recent-arrow'));row.onclick=invoke(()=>detail(env),onError);list.append(row);
 }left.append(list);}else if(!lastUpdated){left.append(el('p',loading?text('loading'):t('ui.b6858ba2e3b7'),'empty-state-message'));}else{
  const empty=el('div',null,'workspace-empty');empty.append(svg('M3 6h7l2 2h9v12H3z M12 11v6 M9 14h6'),el('h3',text('nothing')),el('p',text('nothingHint')));const b=el('button',text('browse'),'btn btn-primary');b.onclick=()=>navigate('catalog-section');empty.append(b);left.append(empty);
 }
 const safety=el('div',null,'data-safety');safety.append(svg('M12 3l8 4v6c0 5-8 8-8 8s-8-3-8-8V7z M8 12l3 3 5-6'));const scopy=el('div');scopy.append(el('strong',text('safety')),el('p',text('safetyHint')));safety.append(scopy);const sb=el('button','→','icon-link');sb.setAttribute('aria-label',text('viewBackups'));sb.onclick=()=>navigate('backups-section');safety.append(sb);left.append(safety);
 const right=el('section',null,'dashboard-panel start-panel');right.append(el('h2',text('quick')));
 for(const [key,tid,path]of [['web','T02','M3 5h18v14H3z M3 9h18 M7 7h.01 M10 7h.01 M9 13l-2 2 2 2 M15 13l2 2-2 2'],['files','T07','M3 7V4h6l2 3h10v13H3z M12 10v7 M9 13l3-3 3 3'],['server','T01','M3 4h18v16H3z M7 9l3 3-3 3 M13 15h4']]){
  const b=el('button',null,'quick-start');b.type='button';b.append(svg(path));const copy=el('span');copy.append(el('strong',text(key)),el('small',text(key+'Hint')));b.append(copy,el('span','↗','recent-arrow'));b.onclick=invoke(()=>choose(tid),onError);right.append(b);
 }
 const helpBox=el('div',null,'help-box');helpBox.append(el('span','✦','help-spark'),el('strong',text('needHelp')),el('p',text('helpHint')));const hb=el('button',text('help')+' →','text-button');hb.onclick=invoke(help,onError);helpBox.append(hb);right.append(helpBox);host.append(left,right);
}

export function renderWorkspaceEnvironments(host,items,ctx){
 const {portal,lifecycle,button,openFiles,openRecords,downloadKey,readOwnedApi,operations,appendOperationTracker,appendCleanupReport,accessInstructions,configurationLabel}=ctx;host.replaceChildren();
 for(const env of items){const card=el('article',null,'card environment-card');card.dataset.environment=env.environment_id;
  const heading=el('div',null,'environment-card-heading');heading.append(templateIcon(env.template_id));const identity=el('div',null,'environment-identity');identity.append(el('small',env.template_id),el('h3',templateText(env)));heading.append(identity,badge(env));card.append(heading);
  card.append(el('p',env.environment_id,'environment-id'));const profile=configurationLabel?.(env);if(profile)card.append(el('p',profile,'environment-profile'));const meta=el('div',null,'environment-meta');
  for(const [label,value]of [['Region',regionLabel(env)],[text('mode'),modeName(operatingPolicy(env).mode)],[text('estimate'),money(env.estimated_committed_milliusd??env.estimate?.total_milliusd)]]){const pair=el('div');pair.append(el('small',label),el('strong',value));meta.append(pair);}card.append(meta);
  const clock=el('div',null,'environment-clock');appendEnvironmentClock(clock,env);card.append(clock);
  if(env.status==='READY')card.append(el('p',accessInstructions(env.template_id),'environment-help'));
  if(env.status==='READY'&&['T02','T03','T04','T05','T06','T09'].includes(env.template_id)&&!env.access_address)card.append(el('p',t('ui.e2cde64ea707'),'warning'));
  if(env.needs_admin)card.append(el('p',t('ui.10f322acd933'),'warning'));
  const provisioning=[...operations.values()].find(op=>op.environment_id===env.environment_id&&['create','restore'].includes(op.action)&&!['SUCCEEDED','FAILED','CANCELLED'].includes(op.status));if(provisioning)appendOperationTracker(card,provisioning);
  const actions=el('div',null,'environment-primary-actions');actions.append(button(text('detail'),()=>lifecycle.detail(env)));const unready=env.status!=='READY'||!!env.lock,link=appLink(env);if(link)actions.append(link);
  if(['T02','T06','T07'].includes(env.template_id))actions.append(button(t('ui.67dd1d6fb247'),()=>openFiles(env),env.status!=='READY'||!!env.lock&&!String(env.lock).startsWith('upload-')));
  if(['T03','T04','T08','T09'].includes(env.template_id))actions.append(button(t('ui.0ce3732c6c81'),()=>openRecords(env),unready));
  if(['T01','T05'].includes(env.template_id))actions.append(button(t('ui.7b014eaf12f3'),()=>downloadKey(env.environment_id),unready));
  if(env.template_id==='T09')actions.append(button(t('ui.bfbaad232cbe'),()=>readOwnedApi(env),unready||!env.access_address));
  card.append(actions);portal.environmentExtras(card,env);
  const menu=el('details',null,'environment-more');menu.append(el('summary',text('manage')));const management=el('div',null,'environment-secondary-actions');lifecycle.controls(management,env);if(management.firstElementChild?.textContent===t('ui.e12d6fabf98e'))management.firstElementChild.remove();menu.append(management);card.append(menu);
  if(env.cleanup_report){const report=el('details',null,'environment-cleanup');report.append(el('summary',text('cleanupReport')));appendCleanupReport(report,env.cleanup_report);card.append(report);}
  host.append(card);
 }
 if(!items.length)host.append(el('p',t('ui.20ae3aa55f42'),'empty-state-message'));
}
