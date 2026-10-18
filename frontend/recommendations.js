import {t,onLanguageChange,money,date,number} from './i18n.js';
import {templateText,profileLabel,regionLabel} from './catalog-text.js';
import {appendCostSummary,missingDescription} from './product-view.js';

export function createRecommendations({api,isAuthenticated,login,onSelect,onClose=()=>{}}){
 const dialog=document.createElement('dialog');dialog.id='recommendations-dialog';dialog.className='recommendations-dialog';dialog.setAttribute('aria-labelledby','rec-title');
 // Every label/result here uses stable translation keys and the locale
 // callback below. Avoid rescanning dynamic workloads/technical evidence with
 // the legacy whole-document phrase translator on every form mutation.
 dialog.setAttribute('translate','no');
 dialog.innerHTML=`<form id="rec-form"><div class="rec-heading"><h2 id="rec-title" data-i18n="rec.title"></h2><button id="rec-close" type="button" class="btn btn-secondary" data-i18n="ui.5d54c2a1a341"></button></div>
 <p data-i18n="rec.intro"></p><p id="rec-notice" class="info-banner" role="status" aria-live="polite"></p>
 <div class="rec-grid"><label><span data-i18n="rec.purpose"></span><select id="rec-template"></select></label>
 <label><span data-i18n="rec.flow"></span><select id="rec-mode"><option value="RECOMMEND" data-i18n="rec.find"></option><option value="ASSESS" data-i18n="rec.assess"></option></select></label>
 <label><span data-i18n="ui.aa7a3573a21d"></span><select id="rec-region"></select></label>
 <label id="rec-profile-field"><span data-i18n="preview.profile"></span><select id="rec-profile"></select></label>
 <label><span data-i18n="preview.horizon"></span><select id="rec-hours"><option>1</option><option>2</option><option>4</option><option>8</option></select><small data-i18n="rec.hoursHint"></small></label>
 <label><span data-i18n="rec.budget"></span><input id="rec-budget" type="number" min="0" max="1000000" step="0.001"><small data-i18n="rec.budgetHint"></small></label></div>
 <details class="rec-policy"><summary data-i18n="rec.operation"></summary><div class="rec-grid">
 <label><span data-i18n="rec.operation"></span><select id="rec-operating"><option value="AUTO_OFF" data-i18n="rec.autoOff"></option><option value="AUTO_RENEW" data-i18n="rec.autoRenew"></option><option value="CONTINUOUS" data-i18n="rec.continuous"></option></select></label>
 <label id="rec-period-field"><span data-i18n="rec.period"></span><select id="rec-period"><option value="5">5</option><option value="15">15</option><option value="60" selected>60</option><option value="240">240</option><option value="480">480</option></select></label>
 <label><span data-i18n="rec.ending"></span><select id="rec-ending"><option value="BACKUP_RETIRE" data-i18n="rec.backupRetire"></option><option value="PAUSE" data-i18n="rec.pause"></option></select></label>
 <label id="rec-renewal-budget-field"><span data-i18n="rec.cumulativeBudget"></span><input id="rec-renewal-budget" type="number" min="0.001" max="1000000" step="0.001" value="10"></label></div><p data-i18n="rec.operationHint"></p></details>
 <div class="rec-actions"><button id="rec-example" type="button" class="btn btn-secondary" data-i18n="rec.useExample"></button><button id="rec-clear" type="button" class="btn btn-ghost" data-i18n="rec.clear"></button></div>
 <p id="rec-example-note" class="info-banner" hidden data-i18n="rec.exampleNote"></p><p data-i18n="rec.unknownHint"></p>
 <div id="rec-fields" class="rec-grid"></div><details><summary data-i18n="rec.advanced"></summary><div id="rec-advanced" class="rec-grid"></div>
 <label><span data-i18n="rec.applicationRevision"></span><input id="rec-application-revision" maxlength="64" pattern="[a-f0-9]{64}"></label>
 <label><span data-i18n="rec.scenarioRevision"></span><input id="rec-scenario-revision" maxlength="64" pattern="[a-f0-9]{64}"></label><p data-i18n="rec.revisionHint"></p></details>
 <div class="rec-actions"><button id="rec-submit" class="btn btn-primary" data-i18n="rec.calculate"></button></div>
 </form><section id="rec-results" aria-live="polite"></section>`;
 document.body.append(dialog);const $=s=>dialog.querySelector(s);let contract=null,openState=false,sequence=0,controller=null,context={},last=null;
 const fields=new Map(),drafts=new Map();let draftTemplate=null;
 function element(tag,text,cls){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(cls)el.className=cls;return el;}
 function option(select,value,text){const o=element('option',text);o.value=value;select.append(o);return o;}
 const regionName=code=>regionLabel({region:code});
 const selected=()=>contract?.templates[$('#rec-template').value];
 const region=()=>selected()?.regions.find(r=>r.region===$('#rec-region').value);
 function translate(){
  for(const el of dialog.querySelectorAll('[data-i18n]'))el.textContent=t(el.getAttribute('data-i18n'));
  for(const el of dialog.querySelectorAll('[data-i18n-aria-label]'))el.setAttribute('aria-label',t(el.getAttribute('data-i18n-aria-label')));
  for(const [key,{input,label,hint,spec}]of fields){label.textContent=t('rec.field.'+key)+(spec.unit?' ('+spec.unit+')':'');hint.textContent=spec.type==='integer'?t('ux.fieldRange',{min:number(spec.minimum),max:number(spec.maximum)}):t('rec.unknown');if(spec.type==='enum'){for(const o of input.querySelectorAll('option'))o.textContent=o.value?t('rec.value.'+o.value):t('rec.unknown');}else input.placeholder=t('rec.unknown');}
  for(const o of $('#rec-template').querySelectorAll('option'))o.textContent=o.value+' · '+templateText({template_id:o.value},'purpose');
  for(const o of $('#rec-region').querySelectorAll('option'))o.textContent=regionName(o.value)+' — '+o.value;
  for(const o of $('#rec-profile').querySelectorAll('option')){const p=region()?.configuration_options.find(p=>p.id===o.value);if(p)o.textContent=profileLabel({template_id:$('#rec-template').value},p);}
  if(last)render(last.result,last.request);
 }
 function invalidate(){sequence++;controller?.abort();controller=null;last=null;$('#rec-results').replaceChildren();$('#rec-submit').disabled=!contract;$('#rec-notice').textContent='';}
 function policies(){
  const mode=$('#rec-operating').value,tid=$('#rec-template').value;
  $('#rec-period-field').hidden=mode==='CONTINUOUS';$('#rec-renewal-budget-field').hidden=mode==='AUTO_OFF';$('#rec-renewal-budget').required=mode==='AUTO_RENEW';
  const pause=$('#rec-ending').querySelector('option[value="PAUSE"]');pause.disabled=!['T01','T05'].includes(tid);if(pause.disabled&&$('#rec-ending').value==='PAUSE')$('#rec-ending').value='BACKUP_RETIRE';
  const continuous=$('#rec-operating').querySelector('option[value="CONTINUOUS"]');continuous.disabled=!(region()?.configuration_options||[]).some(p=>p.operating_modes?.includes('CONTINUOUS'));continuous.hidden=continuous.disabled;
  if(continuous.disabled&&mode==='CONTINUOUS'){$('#rec-operating').value='AUTO_OFF';$('#rec-notice').textContent=t('ux.modeUnavailable');}
  $('#rec-profile-field').hidden=$('#rec-mode').value!=='ASSESS';$('#rec-profile').required=$('#rec-mode').value==='ASSESS';
 }
 function profiles(){
  const prior=$('#rec-profile').value;$('#rec-profile').replaceChildren();
  for(const p of region()?.configuration_options||[])option($('#rec-profile'),p.id,profileLabel({template_id:$('#rec-template').value},p));
  if([...$('#rec-profile').querySelectorAll('option')].some(o=>o.value===prior))$('#rec-profile').value=prior;
  policies();
 }
 function buildFields(){
  if(draftTemplate)drafts.set(draftTemplate,Object.fromEntries([...fields].map(([k,v])=>[k,v.input.value])));draftTemplate=$('#rec-template').value;
  fields.clear();$('#rec-fields').replaceChildren();$('#rec-advanced').replaceChildren();
  for(const spec of selected()?.fields||[]){
   const wrapper=element('label'),label=element('span'),input=element(spec.type==='enum'?'select':'input');
   input.id='rec-input-'+spec.key;input.dataset.workload=spec.key;
   if(spec.type==='enum'){option(input,'',t('rec.unknown'));for(const value of spec.supported_values||spec.values)option(input,value,t('rec.value.'+value));}
   else{input.type='number';input.min=String(spec.minimum);input.max=String(spec.maximum);input.step='1';input.inputMode='numeric';}
   const hint=element('small',spec.type==='integer'?t('ux.fieldRange',{min:number(spec.minimum),max:number(spec.maximum)}):t('rec.unknown'));
   hint.id=input.id+'-hint';input.setAttribute('aria-describedby',hint.id);wrapper.append(label,input,hint);fields.set(spec.key,{input,label,hint,spec,wrapper});$(spec.advanced?'#rec-advanced':'#rec-fields').append(wrapper);
   input.value=drafts.get(draftTemplate)?.[spec.key]??'';
  }
  const old=$('#rec-region').value;$('#rec-region').replaceChildren();for(const r of selected()?.regions||[])option($('#rec-region'),r.region,regionName(r.region)+' — '+r.region);
  $('#rec-region').value=[...$('#rec-region').querySelectorAll('option')].some(o=>o.value===old)?old:contract.default_region;profiles();translate();visibility();
 }
 function visibility(){
  const worker=fields.get('application_kind')?.input.value==='WORKER';
  for(const [key,value]of fields){if(['jobs_per_second','processing_ms','queue_depth'].includes(key)&&$('#rec-template').value==='T06')value.wrapper.hidden=!worker;
   if(['target_rps','response_kib'].includes(key)&&$('#rec-template').value==='T06')value.wrapper.hidden=worker;}
 }
 function readRequest(){
  const workload={};for(const [key,{input,spec,wrapper}]of fields)workload[key]=wrapper.hidden||input.value===''?null:spec.type==='enum'?input.value:Number(input.value);
  const budget=$('#rec-budget').value,mode=$('#rec-operating').value;
  return {mode:$('#rec-mode').value,template_id:$('#rec-template').value,region:$('#rec-region').value,...($('#rec-mode').value==='ASSESS'?{profile_id:$('#rec-profile').value}:{}),
   estimate_hours:Number($('#rec-hours').value),budget_milliusd:budget===''?null:Math.round(Number(budget)*1000),workload,
   operating_policy:{mode,period_minutes:mode==='CONTINUOUS'?null:Number($('#rec-period').value),ending_policy:$('#rec-ending').value,
    budget_limit_milliusd:mode==='AUTO_OFF'||$('#rec-renewal-budget').value===''?null:Math.round(Number($('#rec-renewal-budget').value)*1000)},
   application_revision:$('#rec-application-revision').value||null,scenario_revision:$('#rec-scenario-revision').value||null};
 }
 function line(host,label,value){const row=element('p');row.append(element('strong',label+': '),document.createTextNode(value));host.append(row);}
 function details(title){const d=element('details');d.append(element('summary',title));return d;}
 function render(result,request){
  const host=$('#rec-results');host.replaceChildren(element('h3',t('rec.results')),element('p',t('rec.safety.demandNotCapacity'),'info-banner'));
  const needs=details(t('rec.demand'));for(const [key,value]of Object.entries(result.demand||{}))line(needs,t('rec.metric.'+key),value===null?t('rec.unknown'):number(value));host.append(needs);
  if(Object.keys(result.input_assumptions||{}).length){const defaults=details(t('ux.basicAssumptions'));for(const [key,value]of Object.entries(result.input_assumptions))line(defaults,t('rec.field.'+key),number(value));defaults.append(element('p',t('ux.assumptionsHint')));host.append(defaults);}
  if(result.assessment){const a=result.assessment;const card=element('article',undefined,'rec-assessment');line(card,t('rec.selectedAssessment'),a.resource_assessment?t('rec.status.'+a.resource_assessment.status):t('rec.unavailable'));if(a.resource_assessment?.failures?.length)for(const f of a.resource_assessment.failures)line(card,t('rec.field.'+f.field),t('rec.constraint',{component:f.component,available:f.available}));host.append(card);}
  if(result.status==='NO_MATCH')host.append(element('p',t('rec.noMatch'),'warning'));
  if(!result.options.length){for(const x of result.excluded||[]){host.append(element('p',x.profile_id+' · '+t('rec.exclude.'+x.code)));for(const f of x.details||[])line(host,t('rec.field.'+f.field),t('rec.constraint',{component:f.component,available:f.available}));}}
  const cards=element('div',undefined,'rec-cards');host.append(cards);
  for(const value of result.options){
   const card=element('article',undefined,'card rec-option');card.dataset.profile=value.profile_id;
   card.append(element('h3',profileLabel({template_id:result.template_id},{id:value.profile_id,configuration:value.configuration})),element('p',regionName(value.region)+' — '+value.region));
   if(value.roles.length)card.append(element('p',value.roles.map(role=>t('rec.role.'+role)).join(' · '),'badge'));
   card.append(element('p',t('rec.evidence.'+value.evidence_level)),element('p',t('rec.status.'+value.resource_assessment.status)));
   line(card,t('rec.cost'),value.cost.total_milliusd===null?t('rec.costUnknown'):money(value.cost.total_milliusd));
   line(card,t('rec.budgetStatus'),t('rec.budget.'+value.budget_status));
   if(value.policy_budget_status&&value.policy_budget_status!=='NOT_SET')line(card,t('rec.cumulativeBudget'),t('rec.budget.'+value.policy_budget_status));
   const why=details(t('rec.why'));for(const key of value.reason_keys)why.append(element('p',t(key)));
   if(value.resource_assessment.optional_unchecked_fields?.length)why.append(element('p',t('ux.optionalResources')));
   for(const key of value.resource_assessment.unknown_fields){const go=element('button',t('ux.completeField',{field:t('rec.field.'+key)}),'btn btn-ghost');go.type='button';go.onclick=()=>{const entry=fields.get(key);if(!entry)return;const disclosure=entry.input.closest('details');if(disclosure)disclosure.open=true;entry.input.focus();};why.append(go);}
   if(value.growth_components.length)why.append(element('p',t('rec.growthOnly')+' '+value.growth_components.join(', ')));
   for(const key of value.resource_assessment.guidance_keys)why.append(element('p',t(key)));card.append(why);
   const basis=details(t('rec.basis'));basis.append(element('p',t('rec.safety.notAvailability')));
   if(value.capacity&&value.benchmark){
    line(basis,t('rec.benchmark'),value.benchmark.benchmark_id);line(basis,t('rec.measuredAt'),date(value.benchmark.measured_at));
    line(basis,t('rec.observed'),number(value.capacity.successful_operations_per_second)+' '+value.benchmark.rate_unit);
    line(basis,t('rec.latency'),number(value.capacity.p95_ms)+' ms');line(basis,t('rec.errors'),value.capacity.errors+'/'+value.capacity.attempts);
    line(basis,t('rec.scope'),value.benchmark.generator_location+' · '+value.benchmark.duration_s+' s · '+value.benchmark.cache_state);if(value.benchmark.measurement_scope)basis.append(element('p',value.benchmark.measurement_scope));
    line(basis,t('rec.performance'),t('rec.performance.'+value.performance_status));
   }else basis.append(element('p',t('rec.noBenchmark')));
   for(const e of value.excluded_evidence||[])basis.append(element('p',e.benchmark_id+' · '+t('rec.exclude.'+e.reason)));
   line(basis,t('rec.priceUpdated'),value.cost.price_updated_at||t('rec.unknown'));basis.append(element('p',t('rec.costPolicy')));
   if(value.cost.known_subtotal_milliusd!=null&&value.cost.total_milliusd===null)line(basis,t('rec.knownSubtotal'),money(value.cost.known_subtotal_milliusd));
   appendCostSummary(basis,value.cost);
   for(const code of value.cost.missing_components||[])basis.append(element('p',missingDescription(code),'warning'));
   const technical=details(t('rec.technical'));technical.append(element('pre',JSON.stringify({configuration:value.configuration,units:value.cost.units,assumptions:value.cost.assumptions,missing_components:value.cost.missing_components,unknown:value.cost.unknown},null,2)));basis.append(technical);
   line(basis,t('rec.firstPeriod'),value.first_period.total_milliusd===null?t('rec.unknown'):money(value.first_period.total_milliusd));
   line(basis,t('rec.renewalPeriod'),value.renewal_period.total_milliusd===null?t('rec.unknown'):money(value.renewal_period.total_milliusd));
   line(basis,t('rec.afterShutdown'),value.after_shutdown.total_milliusd===null?t('rec.unknown'):money(value.after_shutdown.total_milliusd));
   card.append(basis);const choose=element('button',t('rec.choose'),'btn btn-primary');choose.type='button';choose.disabled=!value.can_select;
   if(!value.can_select){const reasons=value.selection_blockers?.length?value.selection_blockers:[value.cost.approved?'BUDGET_EXCEEDED':'PRICE_INCOMPLETE'];for(const reason of reasons)card.append(element('p',t('ux.block.'+reason),'warning'));}
   choose.onclick=async()=>{if(choose.disabled||!last)return;choose.disabled=true;try{await onSelect(value,request);close(true);}catch(error){$('#rec-notice').textContent=t('rec.selectionError')+' '+(error.code||'');choose.disabled=false;}};card.append(choose);cards.append(card);
  }
 }
 async function submit(event){
  event.preventDefault();if(!contract||!openState)return;invalidate();const run=sequence,request=readRequest();controller=new AbortController();$('#rec-submit').disabled=true;$('#rec-notice').textContent=t('rec.loading');
  try{const result=await api('/recommendations',{method:'POST',body:JSON.stringify(request),signal:controller.signal});if(sequence!==run||!openState)return;last={result,request};$('#rec-notice').textContent='';render(result,request);}
  catch(error){if(sequence!==run||!openState)return;$('#rec-notice').textContent=t('rec.requestError')+' '+(error.field?t('rec.field.'+error.field)+' · ':'')+(error.code||'');if(fields.has(error.field))fields.get(error.field).input.focus();}
  finally{if(sequence===run)$('#rec-submit').disabled=false;}
 }
 function close(selected=false){invalidate();openState=false;dialog.close();onClose({selected,context});}
 $('#rec-form').onsubmit=submit;$('#rec-close').onclick=()=>close();dialog.addEventListener('cancel',e=>{e.preventDefault();close();});
 $('#rec-form').addEventListener('input',()=>{invalidate();visibility();});
 $('#rec-template').addEventListener('change',()=>{invalidate();$('#rec-example-note').hidden=true;buildFields();$('#rec-notice').textContent=t('ux.templateChanged');});
 $('#rec-region').addEventListener('change',()=>{invalidate();profiles();});
 for(const id of ['rec-mode','rec-operating','rec-ending'])$('#'+id).addEventListener('change',()=>{invalidate();policies();});
 $('#rec-example').onclick=()=>{invalidate();for(const [key,{input}]of fields)input.value=selected()?.sample[key]??'';$('#rec-example-note').hidden=false;visibility();};
 $('#rec-clear').onclick=()=>{invalidate();for(const {input}of fields.values())input.value='';$('#rec-example-note').hidden=true;visibility();};
 const disposeLanguage=onLanguageChange(translate);translate();
 async function open(value={}){
  if(!isAuthenticated())return login();context=value;openState=true;invalidate();contract=null;for(const control of dialog.querySelectorAll('input,select,#rec-example,#rec-clear,#rec-submit'))control.disabled=true;$('#rec-notice').textContent=t('rec.loading');dialog.showModal();
  const run=sequence;
  try{
   const result=await api('/recommendations/schema');if(run!==sequence||!openState)return;contract=result;
   $('#rec-template').replaceChildren();for(const tid of Object.keys(contract.templates))option($('#rec-template'),tid,tid+' · '+templateText({template_id:tid},'purpose'));
   $('#rec-template').value=value.templateId||'T01';buildFields();
   if(value.region){$('#rec-region').value=value.region;profiles();}
   if(value.profileId)$('#rec-profile').value=value.profileId;$('#rec-mode').value=value.assess?'ASSESS':'RECOMMEND';
   const f=value.form||{};$('#rec-hours').value=f.estimateHours||'1';$('#rec-operating').value=f.mode||'AUTO_OFF';$('#rec-period').value=f.periodMinutes||'60';$('#rec-ending').value=f.endingPolicy||'BACKUP_RETIRE';$('#rec-renewal-budget').value=f.budgetUsd||'10';
   for(const [key,{input}]of fields)input.value=value.workload?.[key]??'';
   $('#rec-example-note').hidden=true;$('#rec-notice').textContent='';for(const control of dialog.querySelectorAll('input,select,#rec-example,#rec-clear,#rec-submit'))control.disabled=false;policies();visibility();translate();$('#rec-template').focus();
  }catch(error){if(run===sequence){$('#rec-notice').textContent=t('rec.requestError');$('#rec-submit').disabled=true;}}
 }
 return {open,close,dispose:()=>{disposeLanguage();dialog.remove();},snapshot:()=>({open:openState,last,request:contract?readRequest():null})};
}
