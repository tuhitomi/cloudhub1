import {t} from './i18n.js';

// Lazy, read-only and tied to one owned detail view. Never render template HTML.
export function appendTemplateViewer(host,env,{api,element,timestamp}){
 const button=element('button',t('templateView.open'),'btn btn-secondary template-view-toggle');button.type='button';
 const panel=element('section');panel.className='template-view';panel.hidden=true;
 panel.id='template-view-'+env.environment_id;button.setAttribute('aria-controls',panel.id);button.setAttribute('aria-expanded','false');
 const status=element('p');status.setAttribute('role','status');status.setAttribute('aria-live','polite');
 const content=element('div'),retry=element('button',t('templateView.retry'),'btn btn-secondary');retry.type='button';retry.hidden=true;
 panel.append(element('h3',t('templateView.title')),element('p',t('templateView.notice'),'info-banner'),status,content,retry);
 host.append(button,panel);let serial=0,loaded=false,pending=false;
 async function load(){
  if(pending)return;const run=++serial;pending=true;retry.hidden=true;content.replaceChildren();status.textContent=t('templateView.loading');panel.setAttribute('aria-busy','true');
  try{
   const data=await api('/environments/'+encodeURIComponent(env.environment_id)+'/template');
   if(run!==serial||!host.contains(panel)||panel.hidden)return;
   if(data.source!=='AWS_CLOUDFORMATION_ORIGINAL'||data.environment_id!==env.environment_id||data.read_only!==true||data.redacted!==true||!data.template||!Array.isArray(data.resources))throw {code:'TEMPLATE_FORMAT_UNSUPPORTED'};
   status.textContent=t('templateView.checked')+': '+timestamp(data.retrieved_at)+' · '+data.region;
   content.append(element('p',t('templateView.scope')),element('h4',t('templateView.resources')));
   const list=element('ul');list.className='template-resource-list';
   for(const row of data.resources){const item=element('li');item.append(element('strong',row.logical_id),element('span',row.resource_type));list.append(item);}content.append(list);
   const details=element('details');details.append(element('summary',t('templateView.code')));
   const pre=element('pre',JSON.stringify(data.template,null,2));pre.tabIndex=0;pre.setAttribute('aria-label',t('templateView.code'));details.append(pre);content.append(details);
   content.append(element('p',t('templateView.redactions')+': '+data.redaction_count),element('small',t('templateView.hash')+': '+data.view_sha256));loaded=true;
  }catch(error){
   if(run!==serial||!host.contains(panel)||panel.hidden)return;
   const key={TEMPLATE_UNAVAILABLE:'unavailable',TEMPLATE_ACCESS_UNAVAILABLE:'access',TEMPLATE_FORMAT_UNSUPPORTED:'format',RESOURCE_SCOPE_MISMATCH:'scopeError',NOT_FOUND:'unavailable',UNAUTHORIZED:'login',EMAIL_NOT_VERIFIED:'login'}[error.code]||'error';
   status.textContent=t('templateView.'+key);content.replaceChildren();retry.hidden=false;
  }finally{if(run===serial){pending=false;panel.removeAttribute('aria-busy');}}
 }
 button.onclick=()=>{panel.hidden=!panel.hidden;button.setAttribute('aria-expanded',String(!panel.hidden));button.textContent=t(panel.hidden?'templateView.open':'templateView.close');if(panel.hidden){serial++;pending=false;panel.removeAttribute('aria-busy');}else if(!loaded)void load();};
 retry.onclick=()=>void load();
 return {button,panel,reset(){serial++;pending=false;loaded=false;content.replaceChildren();panel.hidden=true;button.setAttribute('aria-expanded','false');}};
}
