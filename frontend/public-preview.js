import {t,number,money,date,onLanguageChange} from './i18n.js';
import {templateText,profileLabel,regionLabel} from './catalog-text.js';
import {architecture} from './architecture.js';
import {renderQuotaVisual} from './quota-view.js';
export function createPublicPreview({cfg,login,isGuest=()=>true,fetcher=(...args)=>fetch(...args)}){
 const $=s=>document.querySelector(s),dialog=$('#preview-dialog');let catalog,pending,current,preview,run=0,controller,lastError=false;
 const el=(tag,text)=>{const node=document.createElement(tag);if(text!=null)node.textContent=text;return node;};
 function quota(){
  const policy=catalog?.signup_policy;
  const text=policy?t('preview.initialQuota',{count:number(policy.max_active),budget:money(policy.budget_milliusd)})+' '+t('preview.quotaDisclaimer'):t('preview.quotaUnavailable');
  $('#signup-policy').textContent=text;if(isGuest()){$('#limits-summary').textContent=text;renderQuotaVisual(null);}
 }
 async function request(query='',signal){
  if(!cfg.configured)throw Error('not configured');
  const response=await fetcher(cfg.apiBase+'/public/catalog'+query,{credentials:'omit',headers:{Accept:'application/json'},cache:'no-store',signal:signal||AbortSignal.timeout(8000)});
  if(!response.ok)throw Error('preview unavailable');return response.json();
 }
 async function load(){
  if(catalog)return catalog;if(pending)return pending;
  pending=request().then(value=>{if(!Array.isArray(value.items)||!value.signup_policy)throw Error('invalid preview');catalog=value;quota();return value;}).finally(()=>{pending=null;});
  try{return await pending;}catch(error){quota();throw error;}
 }
 function row(){return catalog?.items.find(row=>row.template_id===current?.template_id);}
 function options(){
  const regions=row()?.regions||[];
  for(const [id,values,label] of [['preview-region',regions,r=>regionLabel(r)+' — '+r.region],['preview-profile',regions.find(r=>r.region===current.region)?.configuration_options||[],p=>profileLabel(row(),p)]]){
   const select=$('#'+id),key=id==='preview-region'?'region':'id';select.replaceChildren();
   for(const value of values){const option=el('option',label(value));option.value=value[key];select.append(option);}
   select.value=id==='preview-region'?current.region:current.profile_id;
  }
  $('#preview-hours').value=String(current.hours);
 }
 function hardware(config={}){
  const target=$('#preview-hardware');target.replaceChildren();
  const entries=[['instance_type','EC2'],['vcpu_per_instance','vCPU / EC2'],['memory_gib_per_instance','RAM / EC2','GiB'],
   ['root_gib',t('config.root'),'GiB'],['data_gib',t('config.dataDisk'),'GiB'],['db_class','RDS PostgreSQL'],['db_gib',t('preview.dbDisk'),'GiB'],
   ['nodes','EC2'],['min_instances','EC2 min'],['max_instances','EC2 max'],['cpu','vCPU / ECS',null,1024],['memory_mib','RAM / ECS','MiB'],
   ['lambda_memory_mib','RAM / Lambda','MiB'],['max_files',t('config.files')],['max_file_bytes',t('preview.fileSize'),'KiB',1024],['max_total_bytes',t('preview.totalSize'),'KiB',1024]];
  for(const [key,label,unit,divisor=1]of entries)if(config[key]!=null){const value=typeof config[key]==='number'?number(config[key]/divisor):config[key];target.append(el('dt',label),el('dd',String(value)+(unit?' '+unit:'')));}
  if(config.efs_encrypted)target.append(el('dt','EFS'),el('dd',t('preview.encrypted')));
 }
 function render(){
  if(!current)return;$('#preview-title').textContent=templateText(current)+' · '+t('preview.title');architecture($('#preview-architecture'),current.template_id);
  const cost=$('#preview-cost'),details=$('#preview-price-details');cost.replaceChildren();details.replaceChildren();
  if(!preview){hardware(row()?.regions.find(r=>r.region===current.region)?.configuration_options.find(p=>p.id===current.profile_id)?.configuration);return;}
  hardware(preview.configuration);
  const estimate=preview.estimate;
  $('#preview-status').textContent=t('preview.status.'+preview.status);
  cost.append(el('p',estimate.approved&&estimate.total_milliusd!=null?money(estimate.total_milliusd):t('preview.noPrices')));
  cost.firstChild.className='preview-amount';cost.append(el('p',t('preview.updated',{time:Number.isFinite(Date.parse(estimate.price_updated_at))?date(Date.parse(estimate.price_updated_at)/1000):t('common.unknown')})));
  cost.append(el('p',t('preview.holding',{amount:preview.after_shutdown?.approved?money(preview.after_shutdown.total_milliusd):t('common.unknown')})));
  cost.append(el('p',t('preview.unknown')));
  for(const [label,value]of [[t('preview.unitPrices'),estimate.units],[t('preview.lines'),estimate.lines],[t('preview.assumptions'),estimate.assumptions]]){
   if(!value)continue;details.append(el('h4',label));const pre=el('pre',JSON.stringify(value,null,2));pre.setAttribute('translate','no');details.append(pre);
  }
  details.append(el('p',t('preview.unknown')));
 }
 function close(){run++;controller?.abort();current=null;preview=null;dialog.close();}
 async function refresh(){
  if(!current)return;const id=++run;controller?.abort();controller=new AbortController();preview=null;lastError=false;render();
  $('#preview-status').textContent=t('preview.loading');$('#preview-cost').classList.add('preview-loading');$('#preview-retry').hidden=true;
  try{
   const query=new URLSearchParams(current);const value=await request('?'+query,AbortSignal.any([controller.signal,AbortSignal.timeout(8000)]));
   if(id!==run||!current)return;
   if(value.preview?.template_id!==current.template_id||value.preview?.region!==current.region||value.preview?.profile_id!==current.profile_id||value.preview?.hours!==current.hours)throw Error('mismatched preview');
   preview=value.preview;render();
  }catch(error){if(id!==run||!current||error.name==='AbortError')return;lastError=true;$('#preview-status').textContent=t('preview.error');$('#preview-retry').hidden=false;}
  finally{if(id===run)$('#preview-cost').classList.remove('preview-loading');}
 }
 async function open(template){
  const id=++run;controller?.abort();current={template_id:template.template_id,region:'',profile_id:'',hours:1};preview=null;lastError=false;
  for(const selector of ['#preview-region','#preview-profile'])$(selector).replaceChildren();
  render();$('#preview-status').textContent=t('preview.loading');$('#preview-retry').hidden=true;dialog.showModal();dialog.scrollTop=0;$('#preview-title').setAttribute('tabindex','-1');$('#preview-title').focus({preventScroll:true});
  try{await load();if(id!==run||!current)return;const regions=row()?.regions||[];current.region=regions.some(r=>r.region===catalog.default_region)?catalog.default_region:regions[0]?.region||'';current.profile_id=regions.find(r=>r.region===current.region)?.configuration_options[0]?.id||'';options();await refresh();}
  catch{if(id!==run||!current)return;lastError=true;$('#preview-status').textContent=t('preview.error');$('#preview-retry').hidden=false;}
 }
 $('#preview-region').onchange=()=>{current.region=$('#preview-region').value;current.profile_id=row().regions.find(r=>r.region===current.region)?.configuration_options[0]?.id||'';options();refresh();};
 $('#preview-profile').onchange=()=>{current.profile_id=$('#preview-profile').value;refresh();};
 $('#preview-hours').onchange=()=>{current.hours=Number($('#preview-hours').value);refresh();};
 $('#preview-close').onclick=close;dialog.addEventListener('cancel',event=>{event.preventDefault();close();});
 $('#preview-login').onclick=()=>{close();login();};
 $('#preview-retry').onclick=()=>catalog?refresh():open(current);
 onLanguageChange(()=>{quota();if(current){options();render();if(lastError)$('#preview-status').textContent=t('preview.error');else if(!preview)$('#preview-status').textContent=t('preview.loading');}});
 return {open,load,quota};
}
