import english from './locale-en.js';
import original from './locale-source.js';
export const languages=Object.freeze({'en':'English','vi':'Tiếng Việt','ja':'日本語','ko':'한국어','zh-Hans':'简体中文','fr':'Français','de':'Deutsch','es':'Español'});
export const countryLanguage=country=>({VN:'vi',JP:'ja',KR:'ko',CN:'zh-Hans',FR:'fr',DE:'de',ES:'es'})[String(country||'').toUpperCase()]||'en';
const codes=Object.keys(languages),storageKey='cloudhub.language',cache=new Map([['en',english],['vi',original]]),listeners=new Set(),rendered=new Map();
let locale='en',preference='auto',country=null,sequence=0,dictionary=english,observer,root,savePreference,accountSelection=false,preferencePending=false;
const nativeLocale=()=>locale==='zh-Hans'?'zh-CN':locale;
export const languageState=()=>({locale,preference,country,preferencePending});
export const resolveLanguage=(manual,account,country)=>codes.includes(manual)?manual:codes.includes(account)?account:countryLanguage(country);
export function t(key,values={}){
 const source=dictionary[key]||english[key]||english['common.unavailable']||'Unavailable';
 const value=source.replace(/\{([A-Za-z0-9_]+)\}/g,(all,name)=>Object.hasOwn(values,name)?String(values[name]):all);
 rendered.set(value,{key,values});return value;
}
export const htmlText=(key,values={})=>t(key,values).replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
export const number=(value,options={})=>new Intl.NumberFormat(nativeLocale(),options).format(Number(value));
export const money=milli=>milli==null?t('common.unknown'):new Intl.NumberFormat(nativeLocale(),{style:'currency',currency:'USD',currencyDisplay:'code',minimumFractionDigits:3,maximumFractionDigits:3}).format(Number(milli)/1000);
export const date=seconds=>seconds?new Intl.DateTimeFormat(nativeLocale(),{dateStyle:'medium',timeStyle:'long',timeZone:'Asia/Bangkok'}).format(new Date(Number(seconds)*1000))+' (Asia/Bangkok, UTC+07:00)':t('common.notStarted');
export function onLanguageChange(callback){listeners.add(callback);return()=>listeners.delete(callback);}
function stored(){try{return localStorage.getItem(storageKey);}catch{return null;}}
function remember(value){try{localStorage.setItem(storageKey,value);}catch{/* UI remains usable when browser storage is disabled. */}}
export async function setLanguage(value,{persist=true,loader=async code=>{const r=await fetch(new URL('./locales/'+code+'.json',import.meta.url));if(!r.ok)throw Error('Locale unavailable');return r.json();}}={}){
 if(value!=='auto'&&!codes.includes(value))value='auto';
 const run=++sequence;preference=value;if(persist){accountSelection=true;remember(value);}
 const selected=value==='auto'?countryLanguage(country):value;let next=cache.get(selected),activeLocale=selected;
 if(!next){try{next=await loader(selected);if(!next||typeof next!=='object'||Array.isArray(next))throw Error();cache.set(selected,next);}catch{next=english;activeLocale='en';}}
 if(run!==sequence)return languageState();
 locale=activeLocale;dictionary=next;if(typeof document!=='undefined')document.documentElement.lang=activeLocale;
 translateDOM();for(const fn of listeners)fn(languageState());
 if(persist&&savePreference){let failed=false;try{await savePreference(value);}catch{failed=true;}if(run===sequence){preferencePending=failed;for(const fn of listeners)fn(languageState());}}
 return languageState();
}
export async function accountLanguage(account,save){
 savePreference=save;
 if(accountSelection||stored()!=null){await setLanguage(preference,{persist:false});if(savePreference)try{await savePreference(preference);}catch{}return;}
 const choice=account?.language_preference||'auto';await setLanguage(choice,{persist:false});
}
export async function initializeLanguage({context=async()=>{const r=await fetch('/ui-context',{cache:'no-store',credentials:'omit',signal:AbortSignal.timeout(2500)});if(!r.ok)throw Error();return r.json();}}={}){
 try{const info=await context();country=/^[A-Z]{2}$/.test(info.country_code||'')?info.country_code:null;}catch{country=null;}
 const choice=stored();preference=choice==='auto'||codes.includes(choice)?choice:'auto';accountSelection=choice!=null;
 await setLanguage(preference,{persist:false});return languageState();
}
const bound=new WeakMap(),attrs=new WeakMap(),selectors=new WeakSet();let cachedPairs=[],pairSignature='';
function bindLanguageSelectors(){
 if(!root)return;
 for(const dialog of root.querySelectorAll('dialog'))if(!dialog.querySelector('[data-language-select]')){
  const label=root.createElement('label');label.className='language-control dialog-language-control';
  const text=root.createElement('span');text.setAttribute('data-i18n','language.label');text.textContent=t('language.label');
  const select=root.createElement('select');select.setAttribute('data-language-select','');select.setAttribute('aria-label',t('language.label'));select.setAttribute('data-i18n-aria-label','language.label');label.append(text,select);dialog.prepend(label);
 }
 for(const select of root.querySelectorAll('#language-select,[data-language-select]')){
  if(!selectors.has(select)){select.replaceChildren();for(const [code,label]of [['auto',t('language.auto')],...Object.entries(languages)]){const option=root.createElement('option');option.value=code;option.textContent=label;select.append(option);}select.addEventListener('change',()=>setLanguage(select.value));selectors.add(select);}
  if(select.value!==preference)select.value=preference;
  const automatic=select.querySelector('option[value="auto"]');if(automatic&&automatic.textContent!==t('language.auto'))automatic.textContent=t('language.auto');
 }
}
function renderText(raw){
 if(rendered.has(raw)){const {key,values}=rendered.get(raw);return t(key,values);}
 // Legacy HTML and server messages have stable entries too. Longest matches first.
 const signature=[...cache.keys()].join('|');if(signature!==pairSignature){cachedPairs=[];for(const pack of cache.values())for(const [key,source]of Object.entries(pack))if(typeof source==='string'&&!source.includes('{')&&source.trim().length>1)cachedPairs.push([source,key]);cachedPairs.sort((a,b)=>b[0].length-a[0].length);pairSignature=signature;}
 const pairs=cachedPairs;
 const exact=pairs.find(([source])=>raw.trim()===source.trim());if(exact)return raw.replace(raw.trim(),t(exact[1]));
 let parts=[{text:raw,translated:false}];for(const [source,key]of pairs){parts=parts.flatMap(part=>{if(part.translated||!part.text.includes(source))return[part];const chunks=part.text.split(source),out=[];chunks.forEach((text,i)=>{if(i)out.push({text:t(key),translated:true});out.push({text,translated:false});});return out;});}
 return parts.map(p=>p.text).join('');
}
export function translateDOM(){
 if(!root)return;
 observer?.disconnect();
 bindLanguageSelectors();
 const visit=node=>{
  if(node.nodeType===1&&(/^(SCRIPT|STYLE|PRE|CODE|TEXTAREA)$/.test(node.tagName)||node.getAttribute('translate')==='no'))return;
  if(node.nodeType===3){const previous=bound.get(node);if(previous?.locale===locale&&node.textContent===previous.output)return;const raw=previous&&node.textContent===previous.output?previous.raw:node.textContent;const output=renderText(raw);bound.set(node,{raw,output,locale});if(node.textContent!==output)node.textContent=output;return;}
  if(node.nodeType===1){
   const key=node.getAttribute('data-i18n');if(key&&node.childNodes.length===1&&node.firstChild.nodeType===3){const current=node.firstChild.textContent,prior=bound.get(node.firstChild);if(current===english[key]||current===original[key]||(prior?.key===key&&current===prior.output)){const output=t(key);bound.set(node.firstChild,{key,raw:english[key]||output,output,locale});if(current!==output)node.firstChild.textContent=output;}}
   let previous=attrs.get(node)||{};for(const name of ['placeholder','aria-label','title']){const current=node.getAttribute(name);if(current==null)continue;const prior=previous[name],raw=prior&&current===prior.output?prior.raw:current;const k=node.getAttribute('data-i18n-'+name),output=k?t(k):renderText(raw);previous[name]={raw,output};if(current!==output)node.setAttribute(name,output);}attrs.set(node,previous);
  }
  for(const child of [...node.childNodes||[]]){const prior=bound.get(child);if(prior?.key&&child.textContent===prior.output)continue;visit(child);}
 };visit(root);
 observer?.observe(root,{childList:true,subtree:true,characterData:true,attributes:true,attributeFilter:['placeholder','aria-label','title']});
}
export function installLanguageUI(documentRoot=document){
 root=documentRoot;bindLanguageSelectors();onLanguageChange(()=>{bindLanguageSelectors();const status=documentRoot.querySelector('#language-status');if(status){status.hidden=!preferencePending;status.textContent=preferencePending?t('language.localSaved'):'';}});
 if(typeof MutationObserver!=='undefined')observer=new MutationObserver(translateDOM);translateDOM();
}
export function disposeLanguageUI(){observer?.disconnect();observer=undefined;root=undefined;listeners.clear();savePreference=undefined;accountSelection=false;}
