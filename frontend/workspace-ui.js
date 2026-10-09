import {t,onLanguageChange} from './i18n.js';
const $=s=>document.querySelector(s);
const navigate=id=>window.dispatchEvent(new CustomEvent('cloudhub:navigate',{detail:id}));
$('#workspace-menu').setAttribute('aria-controls','workspace-sidebar');document.querySelector('.app-sidebar').id='workspace-sidebar';
$('#workspace-menu').onclick=()=>{document.body.classList.toggle('workspace-menu-open');$('#workspace-menu').setAttribute('aria-expanded',String(document.body.classList.contains('workspace-menu-open')));};
for(const button of document.querySelectorAll('.workspace-open-catalog'))button.onclick=()=>navigate('catalog-section');
document.addEventListener('keydown',event=>{if(event.key==='Escape'&&document.body.classList.contains('workspace-menu-open')){document.body.classList.remove('workspace-menu-open');$('#workspace-menu').setAttribute('aria-expanded','false');$('#workspace-menu').focus();}if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='k'){event.preventDefault();navigate('catalog-section');$('#catalog-search')?.focus();}});
const search=$('#catalog-search');search?.addEventListener('input',()=>{if(search.value)navigate('catalog-section');});

function enhance(){
 $('#workspace-menu').setAttribute('aria-expanded',String(document.body.classList.contains('workspace-menu-open')));
 for(const dialog of document.querySelectorAll('dialog')){if(dialog.querySelector('.workspace-dialog-close'))continue;const b=document.createElement('button');b.type='button';b.className='workspace-dialog-close';b.textContent='×';b.setAttribute('aria-label',t('ui.5d54c2a1a341'));b.onclick=()=>{const original=dialog.querySelector('#cancel,button[id$="-close"]');if(original)original.click();else dialog.close();};dialog.prepend(b);}
 const quota=$('#create-limits');if(quota&&quota.parentElement.tagName!=='DETAILS'){const d=document.createElement('details'),s=document.createElement('summary');d.className='workspace-create-quota';s.textContent=t('workspace.quotaInfo');quota.before(d);d.append(s,quota);}
 const next=document.querySelector('#quota-visual .quota-next-action');if(next){const disclosure=$('#quota-explanation');disclosure.querySelector('.quota-next-action')?.remove();disclosure.append(next);}
 for(const p of document.querySelectorAll('#environment-detail > p,#quote > p')){
  if(p.dataset.styled)continue;p.dataset.styled='true';const raw=p.textContent,index=raw.indexOf(': ');
  if(index>0&&index<75&&!p.classList.contains('warning')){const label=document.createElement('span'),value=document.createElement('strong');label.textContent=raw.slice(0,index);value.textContent=raw.slice(index+2);p.replaceChildren(label,value);p.classList.add('workspace-key-value');}
 }
 for(const card of document.querySelectorAll('#backups .card')){
  const reasons=new Set(Array.from(card.querySelectorAll('button:disabled')).map(b=>b.title).filter(Boolean));
  for(const reason of reasons){if(card.textContent.includes(reason))continue;const explanation=document.createElement('small');explanation.className='disabled-explanation';explanation.textContent=reason;card.append(explanation);}
 }
}
// Batch layout enhancement into a frame and ignore our own DOM writes. This
// avoids feedback loops with the existing translation observer.
const observation={childList:true,subtree:true,attributes:true,attributeFilter:['open']};
let scheduled=false;
const observer=new MutationObserver(()=>{if(scheduled)return;scheduled=true;requestAnimationFrame(()=>{scheduled=false;observer.disconnect();try{enhance();}finally{observer.observe(document.body,observation);}});});
onLanguageChange(()=>{observer.disconnect();enhance();observer.observe(document.body,observation);});
enhance();observer.observe(document.body,observation);
