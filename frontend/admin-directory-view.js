import {t,number} from './i18n.js';
export function matchesAdminEnvironment(env,query){return [env.environment_id,env.owner_email,env.owner_id,env.template_id,env.status].filter(Boolean).join(' ').toLocaleLowerCase().includes(String(query||'').trim().toLocaleLowerCase());}
export function appendOwner(host,env,element){
 const line=element('p',t('adminDirectory.owner')+': '+(env.owner_email||t('adminDirectory.emailUnknown')),'admin-owner-email');
 host.append(line,element('small',env.owner_id||t('common.unknown')));
}
export function createAccountSearch({api,path,onItems,onSummary,onError,isAdmin}){
 const input=document.querySelector('#admin-user-search'),status=document.querySelector('#admin-user-search-status'),more=document.querySelector('#admin-more-users');
 let generation=0,timer=null,items=[],cursor=null,hidden=0;
 const value=()=>input?.value.trim()||'';
 function message(key,args){if(status)status.textContent=t(key,args);}
 async function load(append=false){
  if(!isAdmin()||append&&!cursor)return;
  clearTimeout(timer);timer=null;
  const run=++generation,query=value(),params=new URLSearchParams();
  if(query)params.set('q',query);if(append)params.set('cursor',cursor);
  if(more)more.disabled=true;message('adminDirectory.loading');
  try{
   const data=await api(path('/admin/users'+(params.size?'?'+params:'')));
   if(run!==generation||query!==value())return;
   items=append?[...new Map([...items,...data.items].map(user=>[user.owner_id||user.username,user])).values()]:data.items;
   hidden=(append?hidden:0)+(data.hidden_test_count||0);cursor=data.next_cursor||null;
   onItems(items);onSummary({...data,hidden_test_count:hidden});
   if(more)more.hidden=!cursor;
   message(cursor?'adminDirectory.partial':items.length?'adminDirectory.count':'adminDirectory.noResults',{count:number(items.length)});
  }catch(error){if(run===generation)message('adminDirectory.failed');throw error;}
  finally{if(run===generation&&more)more.disabled=false;}
 }
 if(input)input.addEventListener('input',()=>{
  generation++;clearTimeout(timer);cursor=null;items=[];hidden=0;onItems(items);if(more){more.hidden=true;more.disabled=true;}
  message('adminDirectory.loading');timer=setTimeout(()=>load().catch(onError),250);
 });
 return {load,reset:()=>{generation++;clearTimeout(timer);cursor=null;items=[];hidden=0;if(input)input.value='';if(status)status.textContent='';if(more){more.hidden=true;more.disabled=false;}onItems(items);}};
}
