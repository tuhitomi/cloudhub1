// Terminal, resize and daily cost views for one environment card.
// All decisions (ownership, state, verification, price) stay in the backend;
// this module only renders responses and forwards explicit user consent.
import {t,money,number} from './i18n.js';
import {SsmSession} from './ssm-session.js';
import {createScreen,write,render,keySequence} from './terminal-screen.js';

const el=(tag,text,cls)=>{const n=document.createElement(tag);if(text!=null)n.textContent=String(text);if(cls)n.className=cls;return n;};
export const TERMINAL_TEMPLATES=new Set(['T01','T05','T08']);
export const RESIZE_TEMPLATES=new Set(['T01','T05']);

function dialog(title){
 const d=el('dialog',null,'cloud-tool-dialog');d.style.maxWidth='min(960px,96vw)';d.style.width='100%';
 const head=el('div',null,'panel-header'),close=el('button',t('cloud.close'),'btn btn-secondary');close.type='button';
 head.append(el('h2',title),close);const body=el('div',null,'cloud-tool-body');d.append(head,body);document.body.append(d);
 close.onclick=()=>d.close();d.addEventListener('close',()=>d.remove());d.showModal();return {dialog:d,body};
}

export function openTerminal(env,{post,node=0,onError,SessionImpl=SsmSession}){
 const {dialog:d,body}=dialog(t('cloud.terminal')+' · '+env.environment_id);
 const status=el('p',t('cloud.terminalConnecting'),'muted'),note=el('small',t('cloud.terminalNote'));
 const screen=createScreen(),view=el('pre',null,'cloud-terminal');view.tabIndex=0;view.setAttribute('role','log');view.setAttribute('aria-live','polite');
 Object.assign(view.style,{background:'#0b1220',color:'#d7e3f4',minHeight:'360px',maxHeight:'60vh',overflow:'auto',padding:'12px',font:'13px/1.4 ui-monospace,Consolas,monospace',whiteSpace:'pre-wrap',wordBreak:'break-all',outline:'none'});
 const end=el('button',t('cloud.terminalEnd'),'btn btn-secondary');end.type='button';
 body.append(status,view,note,end);
 let session,sessionId,closed=false;const decoder=new TextDecoder();
 const finish=async()=>{if(closed)return;closed=true;session?.close();if(sessionId)await post('/environments/'+env.environment_id+'/terminal/'+encodeURIComponent(sessionId)).catch(()=>{});};
 d.addEventListener('close',finish);end.onclick=()=>d.close();
 view.addEventListener('keydown',event=>{const seq=keySequence(event);if(seq==null)return;event.preventDefault();session?.input(seq);});
 view.addEventListener('paste',event=>{event.preventDefault();session?.input(event.clipboardData.getData('text'));});
 const draw=()=>{view.textContent=render(screen);view.scrollTop=view.scrollHeight;};
 post('/environments/'+env.environment_id+'/terminal',{node}).then(started=>{
  if(closed)return post('/environments/'+env.environment_id+'/terminal/'+encodeURIComponent(started.session_id));
  sessionId=started.session_id;
  session=new SessionImpl({streamUrl:started.stream_url,token:started.token,size:{cols:100,rows:28},
   onOutput:bytes=>{write(screen,decoder.decode(bytes,{stream:true}));draw();},
   onState:(state,detail)=>{status.textContent=state==='connected'?t('cloud.terminalConnected'):state==='closed'?t('cloud.terminalClosed'):
    state==='error'?t('cloud.terminalError',{reason:detail||''}):t('cloud.terminalConnecting');if(state==='connected')view.focus();}});
  session.open();
 }).catch(error=>{status.textContent=t('cloud.terminalError',{reason:error.message});onError?.(error);});
 return d;
}

export async function openResize(env,{api,post,keyFor,track,refresh,onError}){
 const {dialog:d,body}=dialog(t('cloud.resize'));
 body.append(el('p',t('cloud.resizeIntro')));
 try{
  const options=await api('/environments/'+env.environment_id+'/resize');
  const usable=options.targets||[];
  if(!usable.length){body.append(el('p',t('cloud.resizeNone'),'muted'));return d;}
  const list=el('div',null,'environment-secondary-actions');
  for(const target of usable){
   const row=el('div',null,'card');row.append(el('strong',target.label));
   const detail=!target.verified?t('cloud.resizeUnverified'):!target.prices_available?t('cloud.resizeNoPrice'):t('cloud.resizeDelta',{amount:money(target.delta_milliusd)});
   row.append(el('p',detail,'muted'));
   const go=el('button',t('cloud.resizeConfirm',{type:target.instance_type}),'btn btn-primary');go.type='button';go.disabled=!target.verified||!target.prices_available;
   go.onclick=async()=>{go.disabled=true;try{
    const body={configuration_id:target.configuration_id,expected_revision:env.lifecycle_revision,expected_delta_milliusd:target.delta_milliusd,confirmed:true};
    track(await post('/environments/'+env.environment_id+'/resize',body,keyFor(env.environment_id+'/resize/'+target.configuration_id)));d.close();await refresh();
   }catch(error){go.disabled=false;onError?.(error);}};
   row.append(go);list.append(row);
  }
  body.append(list);
 }catch(error){body.append(el('p',error.message,'warning'));onError?.(error);}
 return d;
}

export function costChart(series,{width=720,height=220}={}){
 const NS='http://www.w3.org/2000/svg',svg=document.createElementNS(NS,'svg');
 svg.setAttribute('viewBox','0 0 '+width+' '+height);svg.setAttribute('role','img');svg.setAttribute('aria-label',t('cloud.costChart'));svg.style.width='100%';
 const days=series.days||[],pad={l:56,r:12,t:12,b:28},w=width-pad.l-pad.r,h=height-pad.t-pad.b;
 const peak=Math.max(1,...days.map(d=>Math.max(d.estimated_milliusd||0,d.actual_milliusd||0)));
 const x=i=>pad.l+(days.length<=1?w/2:i*w/(days.length-1)),y=v=>pad.t+h-(v/peak)*h,bar=Math.max(4,Math.min(28,w/Math.max(1,days.length)*0.6));
 const node=(tag,attrs,text)=>{const n=document.createElementNS(NS,tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,v);if(text!=null)n.textContent=text;svg.append(n);return n;};
 for(const fraction of [0,.5,1]){const value=peak*fraction;node('line',{x1:pad.l,x2:width-pad.r,y1:y(value),y2:y(value),stroke:'currentColor','stroke-opacity':'.15'});
  node('text',{x:pad.l-6,y:y(value)+4,'text-anchor':'end','font-size':'11',fill:'currentColor'},money(value));}
 days.forEach((d,i)=>{if(d.actual_milliusd!=null)node('rect',{x:x(i)-bar/2,y:y(d.actual_milliusd),width:bar,height:Math.max(1,pad.t+h-y(d.actual_milliusd)),fill:'#2a5ea8',rx:'2'},null)
  .append(Object.assign(document.createElementNS(NS,'title'),{textContent:d.date+' · '+t('cloud.costActual')+' '+money(d.actual_milliusd)}));});
 const points=days.map((d,i)=>d.estimated_milliusd==null?null:x(i)+','+y(d.estimated_milliusd)).filter(Boolean);
 if(points.length)node('polyline',{points:points.join(' '),fill:'none',stroke:'#e07b00','stroke-width':'2','stroke-dasharray':'5 4'});
 const step=Math.max(1,Math.ceil(days.length/8));days.forEach((d,i)=>{if(i%step===0||i===days.length-1)node('text',{x:x(i),y:height-8,'text-anchor':'middle','font-size':'11',fill:'currentColor'},d.date.slice(5));});
 return svg;
}

export async function openCost(env,{api,onError}){
 const {dialog:d,body}=dialog(t('cloud.costChart'));
 try{
  const series=await api('/environments/'+env.environment_id+'/cost-series');
  const legend=el('p',null,'muted');legend.append(el('span','■ ','cost-legend-actual'),t('cloud.costActual')+'   ',el('span','┄ ','cost-legend-estimate'),t('cloud.costEstimated'));
  legend.firstChild.style.color='#2a5ea8';legend.children[1].style.color='#e07b00';
  body.append(el('p',t('cloud.costTotals',{estimated:money(series.estimated_total_milliusd),actual:series.actual_total_milliusd==null?t('cloud.costMissing'):money(series.actual_total_milliusd)})),legend,costChart(series));
  if(series.actual_total_milliusd==null)body.append(el('p',t('cloud.costNoActual'),'info-banner'));
  const table=el('table',null,'data-table'),head=el('tr');for(const k of ['cloud.costDay','cloud.costHours','cloud.costEstimated','cloud.costActual'])head.append(el('th',t(k)));table.append(head);
  for(const day of series.days){const tr=el('tr');tr.append(el('td',day.date),el('td',number(day.running_hours)),el('td',money(day.estimated_milliusd)),el('td',day.actual_milliusd==null?t('cloud.costMissing'):money(day.actual_milliusd)));table.append(tr);}
  const details=el('details');details.append(el('summary',t('cloud.costTable')),table);body.append(details);
  for(const line of series.assumptions||[])body.append(el('small',line));
 }catch(error){body.append(el('p',error.message,'warning'));onError?.(error);}
 return d;
}

export function appendCloudTools(actions,env,ctx){
 const button=(label,action,disabled)=>{const b=el('button',label,'btn btn-secondary');b.type='button';b.disabled=!!disabled;b.onclick=()=>Promise.resolve().then(action).catch(ctx.onError);return b;};
 const unready=env.status!=='READY'||!!env.lock;
 if(TERMINAL_TEMPLATES.has(env.template_id)){
  const count=env.template_id==='T08'?2:1;
  for(let node=0;node<count;node++)actions.append(button(count>1?t('cloud.terminal')+' · '+t('cloud.terminalNode',{n:node+1}):t('cloud.terminal'),()=>openTerminal(env,{...ctx,node}),unready));
 }
 if(RESIZE_TEMPLATES.has(env.template_id))actions.append(button(t('cloud.resize'),()=>openResize(env,ctx),unready));
 actions.append(button(t('cloud.costChart'),()=>openCost(env,ctx),false));
}
