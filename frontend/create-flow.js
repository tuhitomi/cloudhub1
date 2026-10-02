import {t as tr} from './i18n.js';
// GPT-owned creation state. Presentation receives props and calls callbacks only.
const defaults=()=>({region:'',configurationId:'standard',estimateHours:'1',mode:'AUTO_OFF',periodMinutes:'60',endingPolicy:'BACKUP_RETIRE',budgetUsd:'10',appRelease:'',appTitle:'',appSubtitle:''});
const copy=value=>structuredClone(value);
export function regionalTemplate(template,region,configurationId='standard'){
  if(!template?.regions?.length)return template;
  const selected=template.regions.find(r=>r.region===region);
  const modes=selected?.configuration_options?.find(p=>p.id===configurationId)?.operating_modes||selected?.operating_modes;
  return {...template,configuration_options:selected?.configuration_options||[],region_status:selected?.status||'UNAVAILABLE',operating_capabilities:{...template.operating_capabilities,...(modes?{modes}:{})}};
}
export function validateCreation(form,template){
  const errors={};
  if(form.appRelease){const app=template?.application_options?.[form.region]?.find(a=>a.release_id===form.appRelease);if(!app?.enabled||app.configuration_ids&&!app.configuration_ids.includes(form.configurationId||'standard'))errors.appRelease=tr('ux.app.pending');if(!form.appTitle?.trim()||form.appTitle.length>80)errors.appTitle=tr('ux.app.titleRequired');}
  if(template?.regions?.length&&!template.regions.some(r=>r.region===form.region))errors.region=tr("ui.62910444c22e");
  template=regionalTemplate(template,form.region,form.configurationId);
  if(template?.configuration_options?.length&&!template.configuration_options.some(p=>p.id===(form.configurationId||'standard')))errors.configurationId=tr("ui.1c26e8f638a7");
  if(!['1','2','4','8'].includes(form.estimateHours))errors.estimateHours=tr("ui.3ff77a22ab78");
  if(!['CONTINUOUS','AUTO_OFF','AUTO_RENEW'].includes(form.mode))errors.mode=tr("ui.a1ccca43b177");
  if(template?.operating_capabilities?.modes&&!template.operating_capabilities.modes.includes(form.mode))errors.mode=tr("ui.a1ccca43b177");
  if(form.mode!=='CONTINUOUS'&&!['5','15','60','240','480'].includes(form.periodMinutes))errors.periodMinutes=tr("ui.ecae14cb739e");
  const endings=template?.operating_capabilities?.ending_policies||(['T01','T05'].includes(template?.template_id)?['PAUSE','BACKUP_RETIRE']:['BACKUP_RETIRE']);
  if(!endings.includes(form.endingPolicy))errors.endingPolicy=tr("ui.97b75e5742a2");
  if((form.mode==='AUTO_RENEW'||form.mode==='CONTINUOUS'&&form.budgetUsd!=='')&&(!/^\d+(?:\.\d{1,3})?$/.test(form.budgetUsd)||Number(form.budgetUsd)<.001||!Number.isSafeInteger(Math.round(Number(form.budgetUsd)*1000))))errors.budgetUsd=tr("ui.3c62c174bdba");
  return errors;
}
export function creationRequest(template,form,recoveryPoint,planningWorkload){
  template=regionalTemplate(template,form.region);
  const profile=template.configuration_options?.find(p=>p.id===(form.configurationId||'standard'));
  const app=template?.application_options?.[form.region]?.find(a=>a.release_id===form.appRelease);
  return {template_id:template.template_id,...(form.appRelease?{application:{release_id:form.appRelease,revision:app?.revision,title:form.appTitle.trim(),subtitle:form.appSubtitle||'',language:'en'}}:{}),...(planningWorkload?{planning_workload:copy(planningWorkload)}:{}),...(form.region?{region:form.region}:{}),...(profile?{configuration:copy(profile.configuration)}:{}),estimate_hours:Number(form.estimateHours),operating_policy:{mode:form.mode,period_minutes:form.mode==='CONTINUOUS'?null:Number(form.periodMinutes),ending_policy:form.endingPolicy,budget_limit_milliusd:['AUTO_RENEW','CONTINUOUS'].includes(form.mode)&&form.budgetUsd!==''?Math.round(Number(form.budgetUsd)*1000):null,confirmed:true},...(recoveryPoint?{recovery_point:recoveryPoint}:{})};
}
export function createCreationFlow({estimate,create,costAllowed,costError=()=>tr("ui.bd5d070cae13"),onChange=()=>{},onAccepted=()=>{},keyFor,forgetKey=()=>{},now=()=>Date.now(),journal}){
  let state={open:false,step:0,form:defaults(),errors:{},quoteStatus:'idle',quote:null,error:'',busy:false,uncertain:false,consent:false},generation=0,quoteGeneration=0,quoteAt=0;
  const body=()=>creationRequest(state.template,state.form,state.recoveryPoint,state.planningWorkload);
  // The server owns validity. Keep a short transport margin, with a conservative
  // fallback only for legacy/local estimates that do not provide an expiry.
  const remaining=()=>Math.max(0,Math.ceil(((Number(state.quote?.quote_expires_at)>0?Number(state.quote.quote_expires_at)*1000:quoteAt+60000)-now())/1000));
  const fresh=()=>state.quoteStatus==='ready'&&remaining()>3;
  const eligible=()=>fresh()&&regionalTemplate(state.template,state.form.region)?.configuration_options?.find(p=>p.id===state.form.configurationId)?.create_enabled!==false&&state.quote?.configuration_verified!==false&&costAllowed(state.quote);
  function snapshot(){const e=validateCreation(state.form,state.template);return copy({...state,quoteRemainingSeconds:state.quote?remaining():null,template:regionalTemplate(state.template,state.form.region,state.form.configurationId),supportsPause:(state.template?.operating_capabilities?.ending_policies||(['T01','T05'].includes(state.template?.template_id)?['PAUSE']:[])).includes('PAUSE'),canNext:state.open&&!state.busy&&!state.uncertain&&(state.step===0?!e.region&&!e.estimateHours&&!e.configurationId&&!e.appRelease&&!e.appTitle:state.step===1?Object.keys(e).length===0:state.step===2?eligible():false),canSubmit:state.open&&state.step===3&&!state.busy&&state.consent&&(state.uncertain||eligible()),canCancel:!state.busy&&!state.uncertain});}
  function emit(){onChange(snapshot());}
  function invalidate(){quoteGeneration++;state.quote=null;state.quoteStatus='idle';state.consent=false;state.quoteNotice='';quoteAt=0;}
  function open(template,recoveryPoint,restoreConfiguration,restoreRegion){
    if(!(template?.regions?.some(r=>r.configuration_options?.some(p=>p.create_enabled))??template?.create_enabled))throw Error(tr("ui.1b500e658d3d"));
    if(state.busy||state.uncertain)return false;
    const form={...defaults(),region:restoreRegion||template.default_region||''};if(restoreConfiguration){const selected=regionalTemplate(template,form.region).configuration_options?.find(p=>Object.keys(p.configuration).length===Object.keys(restoreConfiguration).length&&Object.entries(p.configuration).every(([k,v])=>restoreConfiguration[k]===v));if(!selected)throw Error(tr("ui.a18849d65aa4"));form.configurationId=selected.id;}
    generation++;quoteGeneration++;state={open:true,step:0,template:copy(template),recoveryPoint,configurationLocked:!!recoveryPoint,form,errors:{},quoteStatus:'idle',quote:null,error:'',busy:false,uncertain:false,consent:false};emit();return true;
  }
  function setWorkload(value){
    if(!state.open||state.busy||state.uncertain)return false;
    state.planningWorkload=value?copy(value):null;invalidate();state.error='';if(state.step>1)state.step=1;emit();return true;
  }
  function change(patch){
    if(!state.open||state.busy||state.uncertain)return;
    const allowed=Object.keys(defaults());let changed=false;
    for(const [key,value]of Object.entries(patch)){if(['configurationId','region'].includes(key)&&state.configurationLocked)continue;if(allowed.includes(key)&&state.form[key]!==String(value)){state.form[key]=String(value);changed=true;}}
    if(!changed)return;
    if('region' in patch){const profiles=regionalTemplate(state.template,state.form.region).configuration_options;state.form.configurationId=profiles?.find(p=>p.create_enabled)?.id||profiles?.[0]?.id||'standard';state.step=0;}
    invalidate();state.errors=validateCreation(state.form,state.template);state.error='';if(state.step>1)state.step=1;emit();
  }
  async function loadQuote({refresh=false}={}){
    if(!state.open||state.busy||state.uncertain||state.quoteStatus==='loading')return;
    state.errors=validateCreation(state.form,state.template);if(Object.keys(state.errors).length){state.step=1;emit();return;}
    const session=generation,run=++quoteGeneration,request=body(),fingerprint=JSON.stringify(request);
    state.quote=null;state.quoteStatus='loading';state.consent=false;state.error='';state.quoteNotice=refresh?tr('experience.quoteRefreshing'):'';emit();
    try{
      const quote=await estimate(request);
      if(!state.open||generation!==session||quoteGeneration!==run||JSON.stringify(body())!==fingerprint)return;
      if(request.region&&quote.region!==request.region)throw Error(tr("ui.15bf58cd69a0"));
      if(!quote?.first_period||!quote.renewal_period||!quote.after_shutdown||!quote.preview||quote.approved&&(!Number.isFinite(quote.total_milliusd)||quote.total_milliusd<0)||quote.estimate_hours!==request.estimate_hours||!Object.entries(request.operating_policy).every(([key,value])=>quote.operating_policy?.[key]===value))throw Error(tr("ui.7f7591c7743e"));
      if(request.configuration&&(!quote.configuration||Object.keys(quote.configuration).length!==Object.keys(request.configuration).length||!Object.entries(request.configuration).every(([k,v])=>quote.configuration[k]===v)))throw Error(tr("ui.8350adb925bd"));
      if(request.planning_workload&&(!quote.planning_workload||Object.keys(quote.planning_workload).length!==Object.keys(request.planning_workload).length||!Object.entries(request.planning_workload).every(([k,v])=>quote.planning_workload[k]===v)))throw Error(tr('rec.quoteMismatch'));
      if(request.application&&(!quote.application||!Object.entries(request.application).every(([k,v])=>quote.application[k]===v)))throw Error(tr('rec.quoteMismatch'));
      state.quote=copy(quote);state.quoteStatus='ready';quoteAt=now();state.quoteNotice=refresh?tr('experience.quoteRefreshed'):'';
      if(quote.configuration_verified===false)state.error=tr("ui.581383befb9a");
      else if(!costAllowed(quote))state.error=costError(quote);
    }catch(error){if(state.open&&session===generation&&run===quoteGeneration){state.quoteStatus='error';state.error=error.message||tr("ui.4a026edb441f");state.quoteNotice='';state.step=2;}}
    emit();
  }
  async function next(){
    if(!state.open||state.busy||state.uncertain)return;
    state.errors=validateCreation(state.form,state.template);
    if(state.step===0){if(state.errors.region||state.errors.estimateHours||state.errors.configurationId||state.errors.appRelease||state.errors.appTitle){emit();return;}state.step=1;emit();return;}
    if(state.step===1){if(Object.keys(state.errors).length){emit();return;}state.step=2;await loadQuote();return;}
    if(state.step===2){if(!fresh()&&state.quoteStatus==='ready'){await loadQuote();return;}if(!eligible()){emit();return;}state.step=3;emit();}
  }
  function back(){if(state.open&&!state.busy&&!state.uncertain&&state.step>0){state.step--;state.error='';state.consent=false;emit();}}
  function consent(value){state.consent=!!value&&state.step===3&&!state.busy&&(state.uncertain||eligible());emit();}
  function cancel(){if(state.busy||state.uncertain)return false;generation++;invalidate();state.open=false;emit();return true;}
  async function reconcile({refresh=false}={}){
    if(state.open&&!state.busy&&!state.uncertain&&state.quoteStatus==='ready'){
      if(refresh&&state.step>=2&&remaining()<=15&&now()-quoteAt>=10000){await loadQuote({refresh:true});return;}
      if(!fresh()){invalidate();state.step=2;state.quoteStatus='error';state.error=tr('experience.quoteExpired');emit();}
    }
  }
  function reset(){generation++;invalidate();state={open:false,step:0,form:defaults(),errors:{},quoteStatus:'idle',quote:null,error:'',busy:false,uncertain:false,consent:false};emit();}
  function restorePending(){
    if(state.open||state.busy)return false;
    const saved=journal?.read();if(!saved)return false;
    generation++;state={...copy(saved.state),open:true,step:3,busy:false,uncertain:true,consent:false,errors:{},error:tr('create.pendingRecovery'),pendingRequest:copy(saved.request),pendingKey:saved.key};emit();return true;
  }
  async function submit(){
    if(!state.open||state.busy||state.step!==3||!state.consent)return;
    if(!state.uncertain&&!eligible()){state.step=2;await loadQuote();return;}
    if(!state.uncertain){state.errors=validateCreation(state.form,state.template);if(Object.keys(state.errors).length){state.step=1;emit();return;}}
    const request=state.pendingRequest||{...body(),...(state.quote?.quote_id?{quote_id:state.quote.quote_id}:{})},scope=JSON.stringify(request),session=generation,requestKey=state.pendingKey||keyFor(scope);
    try{journal?.write({key:requestKey,request,state:copy({...state,pendingRequest:undefined,pendingKey:undefined})});}
    catch{state.error=tr('create.storageUnavailable');emit();return;}
    state.pendingRequest=copy(request);state.pendingKey=requestKey;
    state.busy=true;state.error='';emit();
    let accepted;
    try{
      accepted=await create(request,requestKey);
      if(!accepted?.operation_id)throw Error(tr("ui.ef40cc675fe1"));
      if(session!==generation)return accepted;
      journal?.clear();delete state.pendingRequest;delete state.pendingKey;
      forgetKey(scope);state.open=false;state.busy=false;state.uncertain=false;generation++;invalidate();emit();
    }catch(error){
      if(session===generation){const reviewRequired=error.code?.startsWith('QUOTE_')||error.reviewRequired;state.busy=false;state.uncertain=!reviewRequired&&(!Number.isInteger(error.status)||error.status>=500);if(!state.uncertain){journal?.clear();delete state.pendingRequest;delete state.pendingKey;}if(reviewRequired){invalidate();state.step=2;state.error=tr(error.code==='QUOTE_REQUIRED'?'contract.reload':'quote.review');state.quoteStatus='error';emit();return;}state.error=(error.message||tr("ui.228790f6a4e8"))+(state.uncertain?tr("ui.6b43d54f911a"):tr("ui.8fa57661dfa7"));emit();}
      return;
    }
    // An accepted 202 must not be presented as a failed create when list refresh fails.
    await onAccepted(accepted);
    return accepted;
  }
  return {open,change,setWorkload,next,back,consent,cancel,loadQuote,submit,snapshot,reconcile,restorePending,reset};
}
