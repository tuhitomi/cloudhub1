import {t,date,number} from './i18n.js';
// Views consume backend state only. They never infer AWS component readiness,
// perform writes, estimate completion times, or render untrusted HTML.
const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=String(text);if(cls)n.className=cls;return n;};
const terminal=new Set(['SUCCEEDED','FAILED','CANCELLED']);
export function operationSteps(op){
 if(!['create','restore'].includes(op.action))return [];
 const phase=op.status==='FAILED'?(op.failed_phase||op.phase):op.phase;
 const groups=[['CREATE','WAIT_CREATE'],['READINESS'],['SCHEDULE']],index=groups.findIndex(g=>g.includes(phase));
 if(index<0&&op.status!=='SUCCEEDED')return [];
 return ['provision','readiness','schedule'].map((key,i)=>({key,state:op.status==='SUCCEEDED'?'complete':i<index?'complete':i===index?(op.status==='FAILED'?'failed':op.status==='CANCELLED'?'cancelled':'current'):'pending'}));
}
export function appendOperationTracker(host,op){
 const section=el('section',null,'operation-tracker'),steps=operationSteps(op);
 if(steps.length){const list=el('ol',null,'operation-steps');list.setAttribute('aria-label',t('experience.progress'));
  for(const step of steps){const item=el('li',null,'operation-step');item.dataset.state=step.state;
   const marker=el('span',step.state==='complete'?'✓':step.state==='failed'?'!':'•','operation-step-marker');marker.setAttribute('aria-hidden','true');
   item.append(marker,el('span',t('experience.stage.'+step.key)),el('small',t('experience.state.'+step.state)));
   if(step.state==='current')item.setAttribute('aria-current','step');list.append(item);
  }section.append(list);
 }
 if(op.created_at){const elapsed=el('p',null,'operation-elapsed');elapsed.dataset.started=String(op.created_at);if(terminal.has(op.status))elapsed.dataset.ended=String(op.completed_at||op.finished_at||op.updated_at||'');section.append(elapsed);}
 section.append(el('small',t('experience.updated',{time:op.updated_at?date(op.updated_at):t('common.unknown')})));
 if(!terminal.has(op.status))section.append(el('p',t('experience.noEta'),'muted'));
 host.append(section);updateClocks(section);
}
export function duration(seconds){
 if(!Number.isFinite(seconds))return t('common.unknown');
 const n=Math.max(0,Math.floor(seconds)),two=value=>number(value,{minimumIntegerDigits:2,useGrouping:false});
 return [Math.floor(n/3600),Math.floor(n/60)%60,n%60].map(two).join(':');
}
export function updateClocks(root=document,now=Date.now()){
 for(const node of root.querySelectorAll('[data-deadline]')){
  const left=Math.ceil((Number(node.dataset.deadline)*1000-now)/1000);
  node.textContent=left>0?t('experience.nextAction',{time:duration(left)}):t('experience.deadlineReached');
 }
 for(const node of root.querySelectorAll('[data-started]')){
  const ended=Object.hasOwn(node.dataset,'ended')?Number(node.dataset.ended)*1000:now;
  node.textContent=t('experience.elapsed',{time:ended?duration((ended-Number(node.dataset.started)*1000)/1000):t('common.unknown')});
 }
}
export function appendEnvironmentClock(host,env){
 if(env.operating_policy?.mode==='CONTINUOUS'){host.append(el('p',t('continuous.explanation'),'environment-clock'));return;}
 if(env.status!=='READY'||!Number(env.deadline))return;
 const clock=el('p',null,'environment-clock');clock.dataset.deadline=String(env.deadline);host.append(clock);updateClocks(host);
}
export function renderReleaseStudio(host,data){
 const section=el('section',null,'release-studio');section.setAttribute('aria-label',t('experience.releaseStudio'));
 const states=el('dl',null,'release-states');
 for(const [label,id] of [['active',data.active_release_id],['draft',data.draft_release_id],['previous',data.previous_release_id]]){
  const row=el('div');row.append(el('dt',t('experience.release.'+label)),el('dd',id||t('common.unknown')));states.append(row);
 }section.append(states);
 if(data.write_enabled===false)section.append(el('p',t('experience.prepareDraft'),'info-banner'));
 host.append(section);
}
export function renderRecordResult(host,result){
 host.replaceChildren();const rows=Array.isArray(result)?result:Array.isArray(result?.items)?result.items:Array.isArray(result?.records)?result.records:null;
 if(!rows){host.append(el('p',t('experience.dataUnavailable')));return;}
 const table=el('table',null,'data-table'),caption=el('caption',t('experience.recordCount',{count:number(rows.length)})),head=el('thead'),tr=el('tr');
 for(const label of ['experience.recordId','experience.recordContent']){const th=el('th',t(label));th.setAttribute('scope','col');tr.append(th);}head.append(tr);
 const body=el('tbody');for(const row of rows){const tr=el('tr');tr.append(el('td',row.record_id??row.row_id??row.id??t('common.unknown')),el('td',row.text??row.content??t('common.unknown')));body.append(tr);}
 table.append(caption,head,body);host.append(table);if(!rows.length)host.append(el('p',t('experience.noRecords')));
}
export function createFileDropZone({zone,input,onSelect,onError,allowed=()=>true}){
 zone.tabIndex=0;zone.setAttribute('role','button');zone.setAttribute('aria-label',t('experience.dropFile'));
 zone.addEventListener('click',()=>{if(allowed())input.click();});
 zone.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();if(allowed())input.click();}});
 zone.addEventListener('dragover',event=>{event.preventDefault();zone.classList.toggle('is-dragging',allowed());});
 zone.addEventListener('dragleave',()=>zone.classList.remove('is-dragging'));
 zone.addEventListener('drop',event=>{event.preventDefault();zone.classList.remove('is-dragging');if(!allowed())return;const files=event.dataTransfer?.files;
  if(files?.length!==1){onError(t('experience.oneFile'));return;}
  // Selection only. No upload or replacement consent is triggered by dropping.
  onSelect(files[0]);
 });
}
