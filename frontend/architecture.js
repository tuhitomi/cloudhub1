import {t} from './i18n.js';
// Service topology, not live inventory. No resource identifiers or external SVGs.
const graphs={
 T01:[['user','SSH','EC2','EBS /data']],T02:[['user','CloudFront','S3']],
 T03:[['user','EC2','RDS PostgreSQL']],T04:[['user','ALB','Auto Scaling / EC2','RDS PostgreSQL']],
 T05:[['user','EC2 / Web','EBS /data']],T06:[['user','ALB','ECS Fargate'],['ECS Fargate','S3']],
 T07:[['user','CloudHub API','S3']],T08:[['EC2 (1)','EFS','EC2 (2)']],
 T09:[['user','API Gateway','Lambda','DynamoDB']]
};
export function architecture(host,id,{compact=false}={}){
 host.replaceChildren();const paths=graphs[id];if(!paths)return;
 if(compact){
  const names=paths.flatMap((path,index)=>index?path.slice(1):path),svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
  svg.setAttribute('viewBox',`0 0 400 ${Math.ceil(names.length/2)*68+8}`);svg.setAttribute('role','img');svg.setAttribute('aria-label',t('preview.architecture')+': '+names.map(n=>n==='user'?t('preview.visitor'):n).join(' → '));svg.classList.add('architecture-diagram');
  const point=index=>{const row=Math.floor(index/2),col=row%2?1-index%2:index%2;return {x:col*200+10,y:row*68+6};};
  names.forEach((name,index)=>{const {x,y}=point(index),rect=document.createElementNS(svg.namespaceURI,'rect');for(const [key,value]of Object.entries({x,y,width:176,height:48,rx:8}))rect.setAttribute(key,String(value));svg.append(rect);
   const text=document.createElementNS(svg.namespaceURI,'text');text.setAttribute('x',String(x+88));text.setAttribute('y',String(y+29));text.setAttribute('text-anchor','middle');text.textContent=name==='user'?t('preview.visitor'):name;svg.append(text);
   if(index<names.length-1){const next=point(index+1),edge=document.createElementNS(svg.namespaceURI,'path');const d=next.y!==y?`M ${x+88} ${y+48} V ${next.y-3} l -4 -5 m 4 5 l 4 -5`:next.x>x?`M ${x+176} ${y+24} H ${next.x-3} l -5 -4 m 5 4 l -5 4`:`M ${x} ${y+24} H ${next.x+179} l 5 -4 m -5 4 l 5 4`;edge.setAttribute('d',d);edge.classList.add('architecture-edge');svg.append(edge);}
  });host.append(svg);return;
 }
 const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
 const width=680,rowHeight=94;svg.setAttribute('viewBox',`0 0 ${width} ${paths.length*rowHeight}`);svg.setAttribute('role','img');svg.setAttribute('aria-label',t('preview.architecture'));svg.classList.add('architecture-diagram');
 for(let row=0;row<paths.length;row++){
  const names=paths[row],step=width/names.length;
  names.forEach((name,index)=>{
   const x=step*index+8,y=row*rowHeight+12,w=step-30;
   if(index<names.length-1){const line=document.createElementNS(svg.namespaceURI,'path');line.setAttribute('d',`M ${x+w} ${y+30} H ${x+step-5} l -6 -4 m 6 4 l -6 4`);line.classList.add('architecture-edge');svg.append(line);}
   const rect=document.createElementNS(svg.namespaceURI,'rect');for(const [k,v]of Object.entries({x,y,width:w,height:60,rx:10}))rect.setAttribute(k,String(v));svg.append(rect);
   const text=document.createElementNS(svg.namespaceURI,'text');text.setAttribute('x',String(x+w/2));text.setAttribute('y',String(y+34));text.setAttribute('text-anchor','middle');text.textContent=name==='user'?t('preview.visitor'):name;svg.append(text);
  });
 }
 host.append(svg);
}
