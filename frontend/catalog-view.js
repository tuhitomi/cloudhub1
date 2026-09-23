import {t,number,onLanguageChange} from './i18n.js';
import {templateText} from './catalog-text.js';
import {architecture} from './architecture.js';

// Presentation categories only. Availability, prices and configuration remain API-owned.
const groups={all:[],web:['T02','T07'],compute:['T01','T05','T08'],database:['T03','T04'],modern:['T06','T09']};
const kinds={T01:'compute',T02:'web',T03:'database',T04:'database',T05:'compute',T06:'modern',T07:'web',T08:'compute',T09:'modern'};
const paths={
 T01:'M4 4h16v16H4z M8 9l3 3-3 3 M13 15h3',
 T02:'M3 5h18v14H3z M3 9h18 M7 7h.01 M10 7h.01 M9 13l-2 2 2 2 M15 13l2 2-2 2',
 T03:'M21 6c0 2-4 3-8 3S5 8 5 6s4-3 8-3 8 1 8 3z M5 6v12c0 2 4 3 8 3s8-1 8-3V6 M5 12c0 2 4 3 8 3s8-1 8-3',
 T04:'M12 3v6 M5 14V9h14v5 M2 15h6v6H2z M9 15h6v6H9z M16 15h6v6h-6z',
 T05:'M3 3h18v13H3z M8 21h8 M12 16v5 M6 7h12 M6 11h8',
 T06:'M12 2l9 5v10l-9 5-9-5V7l9-5z M3 7l9 5 9-5 M12 12v10 M7 4l10 6',
 T07:'M3 7V4h6l2 3h10v13H3V7z M12 10v7 M9 13l3-3 3 3',
 T08:'M8 12h8 M7 6H4v12h3 M17 6h3v12h-3 M7 3h10v6H7z M7 15h10v6H7z',
 T09:'M13 2L4 14h7l-1 8 10-13h-7l0-7z'
};
const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;if(cls)n.className=cls;return n;};
const normalized=value=>String(value).normalize('NFKD').replace(/\p{M}/gu,'').toLowerCase().replaceAll('đ','d');
export function templateIcon(id){
 const n=el('span',null,'catalog-icon');n.setAttribute('aria-hidden','true');
 if(paths[id])n.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round"><path d="'+paths[id]+'"/></svg>';
 return n;
}
export function createCatalogView({onSelect,onPreview,accessInstructions=()=>''}={}){
 const host=document.querySelector('#catalog'),toolbar=document.querySelector('#catalog-tools');
 let items=[],guest=true,selected='all',query='';
 if(!host)return {update(){}};
 let chips,search,result;
 if(toolbar){
  const head=el('div',null,'catalog-tools-head'),label=el('label',null,'catalog-search');
  const searchLabel=el('span',t('redesign.search'),'sr-only');search=el('input');search.type='search';search.maxLength=100;search.id='catalog-search';label.append(searchLabel,search);
  result=el('p',null,'catalog-result-count');result.setAttribute('role','status');
  const topbar=document.querySelector('#topbar-search');if(topbar)topbar.replaceChildren(label);else head.append(label);head.append(result);
  chips=el('div',null,'catalog-filters');chips.setAttribute('role','group');toolbar.replaceChildren(chips,head);
  search.addEventListener('input',()=>{query=search.value;renderCards();});
 }
 function visible(){return items.filter(row=>(selected==='all'||groups[selected].includes(row.template_id))&&normalized([row.template_id,templateText(row),templateText(row,'purpose'),...(row.services||[])].join(' ')).includes(normalized(query)));}
 function renderCards(){
  const rows=visible();host.replaceChildren();host.setAttribute('aria-busy','false');
  if(result)result.textContent=t('redesign.results',{count:number(rows.length),total:number(items.length)});
  for(const row of rows){
   const id=row.template_id,kind=kinds[id],card=el('article',null,'card catalog-card');card.dataset.template=id;card.dataset.kind=kind;
   const head=el('div',null,'catalog-card-heading'),identity=el('div',null,'catalog-identity'),tags=el('div',null,'catalog-tags');
   tags.append(el('span',id,'tag catalog-code'),el('span',t('experience.group.'+kind),'catalog-category'));identity.append(tags,el('h3',templateText(row)));head.append(templateIcon(id),identity);
   card.append(head,el('p',templateText(row,'purpose'),'catalog-purpose'));
   const diagram=el('div',null,'catalog-architecture');architecture(diagram,id,{compact:true});card.append(diagram);
   const specs=el('ul',null,'catalog-specs');for(const service of row.services||[])specs.append(el('li',service));card.append(specs);
   const details=el('details',null,'catalog-services');details.append(el('summary',t('ui.e50522f92ecd')),el('p',t('ui.ad31a7141776')+accessInstructions(id)));card.append(details);
   const foot=el('div',null,'catalog-card-actions');
   if(!guest){const status=el('p',row.create_enabled?t('ui.12d6d156ad83'):t('ui.f55bc200b5a1'),'catalog-availability');status.dataset.available=String(!!row.create_enabled);foot.append(status);}
   const actionRow=el('div',null,'catalog-action-row');actionRow.append(el('small',t('redesign.quoteHint'),'catalog-price-hint'));
   const choose=el('button',t('ui.a20b55f7f509'),'btn btn-primary catalog-select');choose.type='button';choose.disabled=!guest&&!row.create_enabled;choose.addEventListener('click',()=>{if(!choose.disabled)onSelect?.(row,{guest});});actionRow.append(choose);foot.append(actionRow);
   if(guest){const preview=el('button',t('preview.open'),'btn btn-secondary catalog-preview');preview.type='button';preview.addEventListener('click',()=>onPreview?.(row));foot.append(preview);}
   card.append(foot);host.append(card);
  }
  if(!rows.length)host.append(el('p',items.length?t('redesign.noResults'):t('ui.20de5201612e'),'empty-state-message'));
 }
 function renderTools(){
  if(!chips)return;search.placeholder=t('redesign.search');search.setAttribute('aria-label',t('redesign.search'));chips.setAttribute('aria-label',t('redesign.filter'));
  // Keep focused controls across routine updates and locale changes.
  if(!chips.children.length)for(const group of Object.keys(groups)){
   const button=el('button');button.type='button';button.dataset.group=group;
   button.addEventListener('click',()=>{selected=group;renderTools();renderCards();});chips.append(button);
  }
  for(const button of chips.children){const group=button.dataset.group,count=group==='all'?items.length:items.filter(row=>groups[group].includes(row.template_id)).length;button.textContent=t(group==='all'?'redesign.group.all':'experience.group.'+group)+' · '+number(count);button.setAttribute('aria-pressed',String(selected===group));button.disabled=count===0;}
 }
 function update(rows,{guest:isGuest=true}={}){items=(rows||[]).filter(row=>Object.hasOwn(kinds,row.template_id));guest=isGuest;renderTools();renderCards();}
 const dispose=onLanguageChange(()=>{renderTools();renderCards();});
 return {update,dispose,snapshot:()=>({group:selected,query,visible:visible().map(row=>row.template_id)})};
}
