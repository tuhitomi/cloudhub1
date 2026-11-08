import {appendCostSummary,appendCleanupReport,backupStatus} from './product-view.js';
import {operationPresentation} from './presentation-data.js';
import {backupScope} from './catalog-text.js';
import {t as tr,money} from './i18n.js';
import {errorText} from './error-text.js';
import {appendTemplateViewer} from './template-view.js';
// Lifecycle decisions and their cost/data consent; all authorization stays at the backend.
export const operatingPolicy=env=>env.operating_policy||{mode:'AUTO_OFF',period_minutes:Number(env.duration_hours||1)*60,ending_policy:'BACKUP_RETIRE',budget_limit_milliusd:null,source:'legacy_no_auto_renew'};
export const usd=money;
export const modeName=value=>value==='CONTINUOUS'?tr('continuous.name'):value==='AUTO_RENEW'?tr("ui.0b686847e426"):tr("ui.cb445c400428");
export const endingName=value=>value==='PAUSE'?tr("ui.5f1cf53646dd"):tr("ui.4b1633df8952");

export function createLifecycleUI({api,mutate,track,refresh,element,timestamp,notice}){
  const $=s=>document.querySelector(s);let createTemplate,managed,action,currentQuote,serial=0,managementFingerprint='',managementBusy=false;
  const canPause=env=>['T01','T05'].includes(env.template_id);
  function endings(select,env,selected='BACKUP_RETIRE'){
    select.replaceChildren();for(const value of canPause(env)?['BACKUP_RETIRE','PAUSE']:['BACKUP_RETIRE']){const option=element('option',endingName(value));option.value=value;select.append(option);}select.value=selected;
  }
  function policy(mode,period,ending,budget){return {mode,period_minutes:mode==='CONTINUOUS'?null:Number(period),ending_policy:ending,budget_limit_milliusd:['AUTO_RENEW','CONTINUOUS'].includes(mode)&&budget!==''?Math.round(Number(budget)*1000):null,confirmed:true};}
  function configureCreate(template){
    createTemplate=template;$('#operating-mode').value='AUTO_OFF';$('#operating-period').value='60';$('#operating-budget').value='10';
    endings($('#ending-policy'),template);$('#pause-support').textContent=canPause(template)?tr("ui.a40f6d2ed233"):tr("ui.f094e7637298");
    toggleCreate();
  }
  function toggleCreate(){const renewing=$('#operating-mode').value==='AUTO_RENEW';$('#operating-budget-field').hidden=!renewing;$('#operating-budget').required=renewing;
    $('#operating-explanation').textContent=renewing?tr("ui.bfe7e9e494e3"):tr("ui.16d79b5af5c4");
  }
  function createRequest(){return {template_id:createTemplate.template_id,estimate_hours:Number($('#hours').value),operating_policy:policy($('#operating-mode').value,$('#operating-period').value,$('#ending-policy').value,$('#operating-budget').value)};}
  function renderQuote(data){
    const host=$('#quote');host.replaceChildren();
    if(!data.first_period){host.append(element('p',tr("ui.cd3afc2bda48")));return;}
    const rows=[[tr("ui.37994610d585")+data.estimate_hours+tr("ui.8a94bb173e0a"),data.preview.total_milliusd],
      [tr("ui.6025fbc799bb")+data.operating_policy.period_minutes+tr("ui.cf728a6aa3dd"),data.first_period.total_milliusd],
      [tr("ui.f879ef3725af")+data.operating_policy.period_minutes+tr("ui.cf728a6aa3dd"),data.renewal_period.total_milliusd],
      [tr("ui.1a752bb6af14")+data.after_shutdown.period_hours+tr("ui.9e4dcadbbda6"),data.after_shutdown.total_milliusd],
      [tr("ui.aa6ad28a683c"),data.initial_commitment_milliusd]];
    for(const [label,value] of rows)host.append(element('p',label+': '+usd(value)));
    host.append(element('p',tr('cost.budgetScope')),element('p',tr("ui.7baae0306844")),
      element('small',tr("ui.75e06b215ff2")+(data.first_period.price_updated_at||tr("ui.9e24064ac250"))+' · Region: '+(data.first_period.region||tr("ui.9e24064ac250"))));
    if(data.budget_feasible===false)host.append(element('p',tr("ui.be44b2c62beb"),'warning'));
    host.append(element('p',tr('ux.cost.coverage')));appendCostSummary(host,data.first_period);
    const details=element('details');details.append(element('summary',tr("ui.53dae0ff29d0")),element('pre',JSON.stringify({first:data.first_period,renewal:data.renewal_period,after_shutdown:data.after_shutdown},null,2)));host.append(details);
  }
  function field(id,label,type,value){const wrapper=element('label',label),input=element('input');input.id=id;input.type=type;input.required=true;input.value=value;wrapper.append(input);return wrapper;}
  function select(id,label,values,value){const wrapper=element('label',label),input=element('select');input.id=id;for(const [key,text] of values){const option=element('option',text);option.value=key;input.append(option);}input.value=value;wrapper.append(input);return wrapper;}
  const names={renew:tr("ui.b2e1094c40f6"),change_policy:tr("ui.269cf0d04e29"),resume_paused:tr("ui.0de644e43592"),end:tr("ui.2eda469256d5"),destroy:tr("ui.4b1633df8952"),backup:tr("ui.f5568fcc5a74")};
  function request(){
    const body={action};
    if(action==='renew')body.minutes=Number($('#management-minutes').value);
    if(action==='change_policy')body.operating_policy=policy($('#management-mode').value,$('#management-period').value,$('#management-ending').value,$('#management-budget').value);
    return body;
  }
  function updateManagementSubmission(){
    $('#management-submit').disabled=managementBusy||!currentQuote?.approved||!$('#management-confirmed').checked||managementFingerprint!==JSON.stringify(request());
  }
  $('#management-confirmed').addEventListener('change',updateManagementSubmission);
  function managementQuoteRetry(message){
    const retry=element('button',tr("ui.669b16cf0245"));retry.type='button';retry.id='management-retry-quote';retry.className='btn btn-secondary';retry.onclick=updateManagementQuote;
    $('#management-quote').replaceChildren(element('p',message),retry);
  }
  async function updateManagementQuote(){
    const run=++serial;currentQuote=null;managementFingerprint='';$('#management-confirmed').checked=false;$('#management-submit').disabled=true;$('#management-quote').replaceChildren(element('p',tr("ui.0525397ee383")));$('#management-notice').textContent='';
    if(action==='change_policy'){const renewing=$('#management-mode').value==='AUTO_RENEW';const budget=$('#management-budget');budget.required=renewing;budget.disabled=!renewing;budget.parentElement.hidden=!renewing&&$('#management-mode').value!=='CONTINUOUS';$('#management-period').disabled=$('#management-mode').value==='CONTINUOUS';}
    try{
      const fingerprint=JSON.stringify(request());const quote=await api('/environments/'+managed.environment_id+'/management-estimate',{method:'POST',body:fingerprint});
      if(run!==serial||fingerprint!==JSON.stringify(request()))return;currentQuote=quote;managementFingerprint=fingerprint;$('#management-quote').replaceChildren(element('p',tr("ui.64b113df7312")+usd(quote.additional_commitment_milliusd)),element('p',tr("ui.b2685077295f")+usd(quote.cumulative_after_milliusd)),
        element('p',tr("ui.8b9cde06909e")+usd(quote.after_shutdown.total_milliusd)+' / '+quote.after_shutdown.period_hours+tr("ui.9e4dcadbbda6")),element('p',tr('ux.cost.coverage')),element('p',tr("ui.8b2eab78810a")));
      if(quote.review_kind==='TERMINATION_DATA_CONSENT')$('#management-quote').replaceChildren(element('p',tr('termination.review')));
      const details=element('details');details.append(element('summary',tr("ui.d19a56d75832")),element('pre',JSON.stringify(quote,null,2)));$('#management-quote').append(details);updateManagementSubmission();$('#management-notice').textContent='';
    }catch(error){if(run===serial){$('#management-notice').textContent=error.message;managementQuoteRetry(tr("ui.9d1b1c5b0c07"));}}
  }
  async function openManagement(env,nextAction){
    if(managementBusy)return;const opening=++serial;const fresh=await api('/environments/'+env.environment_id);if(opening!==serial)return;managed=fresh;action=nextAction;const p=operatingPolicy(managed);
    $('#management-title').textContent=names[action];$('#management-fields').replaceChildren();$('#management-notice').textContent='';$('#management-quote').replaceChildren();
    const explanations={renew:tr("ui.0f86327d5ddf"),
      change_policy:tr("ui.f5e1e94095c7"),
      resume_paused:tr("ui.9dd179269e2a"),
      end:tr("ui.a5a429fce5b1")+endingName(p.ending_policy)+tr("ui.986260fc273f"),
      destroy:tr("ui.2a1a44bd3f1d"),
      backup:tr("ui.b787103a1d9e")};
    $('#management-description').textContent=explanations[action];
    if(action==='renew'){const f=field('management-minutes',tr("ui.d6c9ae842abf"),'number',p.period_minutes);f.querySelector('input').min=5;f.querySelector('input').max=480;f.querySelector('input').step=1;$('#management-fields').append(f);}
    if(action==='change_policy'){
      $('#management-fields').append(select('management-mode',tr("ui.be2836c8bcf2"),[...(managed.continuous_available?[['CONTINUOUS',tr('continuous.name')]]:[]),['AUTO_OFF',tr("ui.cb445c400428")],['AUTO_RENEW',tr("ui.0b686847e426")]],p.mode),field('management-period',tr("ui.6113a2895447"),'number',p.period_minutes),
        select('management-ending',tr("ui.f4e1e4d793c3"),canPause(env)?[['BACKUP_RETIRE',tr("ui.4b1633df8952")],['PAUSE',tr("ui.5f1cf53646dd")]]:[['BACKUP_RETIRE',tr("ui.4b1633df8952")]],p.ending_policy),
        field('management-budget',tr("ui.2b8901f323f8"),'number',p.budget_limit_milliusd==null?Math.max(10,Number(managed.estimated_committed_milliusd||managed.estimate?.total_milliusd||0)/1000):Number(p.budget_limit_milliusd)/1000));
      $('#management-period').min=5;$('#management-period').max=480;$('#management-period').step=1;$('#management-budget').min='.001';$('#management-budget').step='.001';
    }
    for(const control of $('#management-fields').querySelectorAll('input,select')){
      control.addEventListener('input',()=>{serial++;currentQuote=null;managementFingerprint='';$('#management-confirmed').checked=false;$('#management-submit').disabled=true;managementQuoteRetry(tr("ui.41be9a4078c3"));});
      control.addEventListener('change',updateManagementQuote);
    }
    $('#management-dialog').showModal();await updateManagementQuote();
  }
  $('#management-form').onsubmit=async event=>{
    event.preventDefault();if(managementBusy||!currentQuote?.approved||!$('#management-confirmed').checked||managementFingerprint!==JSON.stringify(request()))return;managementBusy=true;$('#management-submit').disabled=true;$('#management-close').disabled=true;
    for(const field of $('#management-fields').querySelectorAll('input,select'))field.disabled=true;
    const chosen=request();const body=action==='change_policy'?{operating_policy:chosen.operating_policy,expected_revision:Number(managed.lifecycle_revision||0),quote_id:currentQuote.quote_id}:
      (action==='backup'||action==='destroy'&&currentQuote.review_kind!=='TERMINATION_DATA_CONSENT')?{quote_id:currentQuote.quote_id}:{confirmed:true,expected_revision:Number(managed.lifecycle_revision||0),quote_id:currentQuote.quote_id,...(action==='renew'?{minutes:chosen.minutes,quote_id:currentQuote.quote_id}:{})};
    try{const op=await mutate('/environments/'+managed.environment_id+'/'+action,body);track(op);$('#management-dialog').close();serial++;currentQuote=null;managementFingerprint='';try{await refresh();}catch(error){notice(tr("ui.5e23e04f8507")+op.operation_id+tr("ui.6420e2fb2719")+error.message+tr("ui.574cc151141b"));}}
    catch(error){$('#management-notice').textContent=error.message;if(error.code?.startsWith('QUOTE_')||error.reviewRequired){currentQuote=null;$('#management-confirmed').checked=false;managementQuoteRetry(tr('quote.review'));}}finally{managementBusy=false;$('#management-close').disabled=false;for(const field of $('#management-fields').querySelectorAll('input,select'))field.disabled=false;updateManagementSubmission();}
  };
  $('#management-close').onclick=()=>{if(managementBusy)return;$('#management-dialog').close();serial++;currentQuote=null;managementFingerprint='';$('#management-confirmed').checked=false;$('#management-submit').disabled=true;};
  $('#management-dialog').addEventListener('cancel',event=>{event.preventDefault();$('#management-close').onclick();});
  async function detail(env){
    const [fresh,history]=await Promise.all([api('/environments/'+env.environment_id),api('/environments/'+env.environment_id+'/renewals')]);const p=operatingPolicy(fresh);const host=$('#environment-detail');host.replaceChildren();
    for(const [label,value] of [[tr("ui.e16f1ec37c00"),fresh.environment_id],[tr("ui.be2836c8bcf2"),modeName(p.mode)],[tr("ui.002c1f583f54"),p.mode==='CONTINUOUS'?tr('continuous.noDeadline'):p.period_minutes+tr("ui.cf728a6aa3dd")],[tr("ui.f4e1e4d793c3"),endingName(p.ending_policy)],
      [tr("ui.360ca8a8bc5b"),p.mode==='CONTINUOUS'?tr('continuous.noDeadline'):fresh.status==='PAUSED'?tr("ui.bcb5e28faba8"):timestamp(fresh.deadline)],[tr("ui.8439c4862f23"),(fresh.estimate_hours||fresh.duration_hours)+tr("ui.277d3cdff7a8")],
      [tr("ui.30e8417e142e"),usd(fresh.first_period_estimate?.total_milliusd??fresh.estimate?.total_milliusd)],[tr("ui.32719b57ce9b"),usd(fresh.estimated_committed_milliusd??fresh.estimate?.total_milliusd)],
      [tr("ui.9d529bff3f27"),p.budget_limit_milliusd==null?tr("ui.531ac4398542"):usd(p.budget_limit_milliusd)],[tr("ui.8d1b4c956665"),fresh.schedule_pending?tr("ui.500beb24f447"):tr("ui.be5e1f156cf6")]])host.append(element('p',label+': '+value));
    const d=fresh.detail||{};
    if(d.pending_upload){host.append(element('p',tr('upload.progress',{percent:'…'})+' · '+d.pending_upload.upload_id+' · '+timestamp(d.pending_upload.complete_until)));const cancel=element('button',tr('upload.cancel'));cancel.onclick=async()=>{const r=await mutate('/environments/'+fresh.environment_id+'/uploads/'+d.pending_upload.upload_id+'/cancel',{});if(r.operation_id)track(await api('/operations/'+r.operation_id));await refresh();$('#environment-detail-dialog').close();};host.append(cancel);}
    host.append(element('h3',tr('detail.access')),element('p',fresh.access_address||fresh.instance_id||tr('common.unavailable')));
    host.append(element('p',tr('detail.scope')+': '+backupScope(fresh)));
    if(d.current_operation)host.append(element('p',tr('detail.operation')+': '+d.current_operation.operation_id+' · '+operationPresentation(d.current_operation).title+' · '+operationPresentation(d.current_operation).phase+' · '+timestamp(d.current_operation.updated_at||d.current_operation.created_at)));
    const readiness=d.readiness||{infrastructure_ready_at:fresh.ready_at||d.current_operation?.infrastructure_ready_at,data_verified_at:['create','restore'].includes(d.current_operation?.action)?d.current_operation?.data_verified_at:null};
    host.append(element('p',tr('detail.infrastructure')+': '+(readiness.infrastructure_ready_at?tr('detail.yes')+' · '+timestamp(readiness.infrastructure_ready_at):tr('detail.pending'))),element('p',tr('detail.data')+': '+(readiness.data_verified_at?tr('detail.yes')+' · '+timestamp(readiness.data_verified_at):tr('detail.pending'))));
    if(fresh.application)host.append(element('h3',tr('ux.app.heading')),element('p',fresh.application.title+' · '+fresh.application.release_id),element('p',tr('ux.app.scope')));
    if(fresh.continuous_cost_observation){const observation=fresh.continuous_cost_observation;host.append(element('p',observation.status==='PRICES_UNAVAILABLE'?tr('continuous.pricesUnavailable'):tr('continuous.name')+' · '+usd(observation.estimated_milliusd)+' · '+timestamp(observation.checked_at)));}
    if(d.latest_backup)host.append(element('p',tr('detail.backup')+': '+d.latest_backup.recovery_point+' · '+backupStatus(d.latest_backup.status)+' · '+timestamp(d.latest_backup.created_at)+' → '+(['DELETED','DELETING'].includes(d.latest_backup.status)?tr('ux.backup.DELETED'):timestamp(d.latest_backup.retain_until))));
    host.append(element('p',tr('detail.actual')+': '+usd(d.actual_cost?.actual_milliusd)+' · '+timestamp(d.actual_cost?.checked_at)));
    host.append(element('p',tr('detail.support')+': '+fresh.environment_id));
    host.append(element('p',tr("ui.f43b60ef39fd")));
    if(fresh.renewal_blocked_reason)host.append(element('p',tr("ui.13217068fa49")+errorText(fresh.renewal_blocked_reason),'warning'));
    if(fresh.cost_plan?.after_shutdown)host.append(element('p',tr("ui.8b9cde06909e")+usd(fresh.cost_plan.after_shutdown.total_milliusd)+' / '+fresh.cost_plan.after_shutdown.period_hours+tr("ui.f581b11811cf")));
    host.append(element('h3',tr("ui.8548452d63b3")));for(const op of history.items)host.append(element('p',timestamp(op.created_at)+' · '+(op.automatic?tr("ui.a25c80286728"):tr("ui.8c544b74093b"))+' · '+op.status+' · '+usd(op.period_estimate?.total_milliusd)+tr("ui.98f00225c813")+timestamp(op.deadline)));
    if(!history.items.length)host.append(element('p',tr("ui.d69510bf23f5")));if(history.truncated)host.append(element('p',tr("ui.ec85e33b9719")+history.total_count+tr("ui.fc75a08a9b54")));
    const report=fresh.status==='PAUSED'?fresh.pause_report:fresh.cleanup_report;if(report)appendCleanupReport(host,report);
    appendTemplateViewer(host,fresh,{api,element,timestamp});
    $('#environment-detail-dialog').showModal();if(typeof window!=='undefined')window.dispatchEvent(new CustomEvent('cloudhub:detail',{detail:fresh}));
  }
  $('#environment-detail-close').onclick=()=>$('#environment-detail-dialog').close();
  function controls(card,env){
    const add=(label,fn,disabled=false,dangerous=false)=>{const b=element('button',label);b.disabled=disabled;if(dangerous)b.dataset.dangerous='true';b.onclick=()=>Promise.resolve(fn()).catch(error=>notice(error.message));card.append(b);};
    add(tr("ui.e12d6fabf98e"),()=>detail(env));
    if(['READY','PAUSED'].includes(env.status))add(tr("ui.7d6ce7f9017e"),()=>openManagement(env,'change_policy'),!!env.lock||!!env.schedule_pending);
    if(env.status==='READY'){if(operatingPolicy(env).mode!=='CONTINUOUS')add(tr("ui.b2e1094c40f6"),()=>openManagement(env,'renew'),!!env.lock||!!env.schedule_pending);add(tr("ui.2eda469256d5"),()=>openManagement(env,'end'),!!env.lock,true);add(tr("ui.beac6991a434"),()=>openManagement(env,'backup'),!!env.lock);}
    if(env.status==='PAUSED')add(tr("ui.790559358855"),()=>openManagement(env,'resume_paused'),!!env.lock);
    if(['READY','PAUSED','ERROR_RETAINED','CREATE_FAILED'].includes(env.status))add(tr("ui.4b1633df8952"),()=>openManagement(env,'destroy'),!!env.lock,true);
  }
  return {configureCreate,toggleCreate,createRequest,renderQuote,controls,detail,openManagement};
}
