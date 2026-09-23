import {onLanguageChange} from './i18n.js';
export function installAppearance({documentRoot=document,storage,media}={}){
 const select=documentRoot.querySelector('#theme-select');if(!select)return;
 try{storage??=localStorage;}catch{}
 media??=typeof matchMedia==='function'?matchMedia('(prefers-color-scheme: dark)'):null;
 let preference='dark';try{preference=storage?.getItem('cloudhub.theme')||'dark';}catch{}
 if(!['light','dark','system'].includes(preference))preference='dark';
 const apply=()=>{documentRoot.documentElement.dataset.theme=preference==='system'?(media?.matches?'dark':'light'):preference;select.value=preference;};
 const change=()=>{preference=['light','dark','system'].includes(select.value)?select.value:'system';try{storage?.setItem('cloudhub.theme',preference);}catch{}apply();};
 select.addEventListener('change',change);media?.addEventListener?.('change',apply);const off=onLanguageChange(apply);apply();
 return ()=>{select.removeEventListener('change',change);media?.removeEventListener?.('change',apply);off();};
}
