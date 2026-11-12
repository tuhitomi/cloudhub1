import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {parseHTML} from 'linkedom';
import {setLanguage} from '../frontend/i18n.js';
import {encode,decode,uuidToBytes,bytesToUuid,handshakeResponse,SsmSession,PAYLOAD} from '../frontend/ssm-session.js';
import {createScreen,write,render,keySequence} from '../frontend/terminal-screen.js';
import {costChart,appendCloudTools} from '../frontend/cloud-tools.js';

const ID='0f1e2d3c-4b5a-6978-8796-a5b4c3d2e1f0';
const tick=()=>new Promise(resolve=>setImmediate(resolve));

test('Session Manager header layout matches the plugin wire format',async()=>{
 const buffer=await encode({messageType:'input_stream_data',sequenceNumber:7,flags:0,messageId:ID,payloadType:PAYLOAD.output,payload:'ls\r',createdDate:1700000000000});
 const view=new DataView(buffer),bytes=new Uint8Array(buffer);
 assert.equal(view.getUint32(0),116);
 assert.equal(new TextDecoder().decode(bytes.slice(4,36)),'input_stream_data'.padEnd(32,' '));
 assert.equal(view.getUint32(36),1);assert.equal(view.getUint32(116),3);assert.equal(view.getUint32(112),1);
 assert.deepEqual(bytes.slice(80,112),new Uint8Array(createHash('sha256').update('ls\r').digest()));
 // UUID halves are swapped on the wire: least significant 8 bytes first.
 assert.equal([...bytes.slice(64,72)].map(b=>b.toString(16).padStart(2,'0')).join(''),'8796a5b4c3d2e1f0');
 const parsed=decode(buffer);
 assert.equal(parsed.messageType,'input_stream_data');assert.equal(parsed.sequenceNumber,7);assert.equal(parsed.messageId,ID);
 assert.equal(new TextDecoder().decode(parsed.payload),'ls\r');
});

test('UUID conversion is reversible',()=>{assert.equal(bytesToUuid(uuidToBytes(ID)),ID);assert.throws(()=>uuidToBytes('nope'));});

test('handshake accepts the shell session and declines encryption it cannot do',()=>{
 const reply=handshakeResponse({RequestedClientActions:[{ActionType:'SessionType'},{ActionType:'KMSEncryption'}]});
 assert.deepEqual(reply.ProcessedClientActions.map(a=>[a.ActionType,a.ActionStatus]),[['SessionType',1],['KMSEncryption',2]]);
});

class FakeSocket{constructor(url){this.url=url;this.sent=[];this.readyState=1;FakeSocket.last=this;}send(data){this.sent.push(data);}close(){this.onclose?.();}}
const output=(seq,payloadType,text)=>encode({messageType:'output_stream_data',sequenceNumber:seq,messageId:globalThis.crypto.randomUUID(),payloadType,payload:text});

test('session opens with the token, acknowledges output and delivers it in order',async()=>{
 const seen=[],states=[];
 const session=new SsmSession({streamUrl:'wss://ssmmessages.ap-southeast-1.amazonaws.com/v1/data-channel/s-1?role=publish_subscribe',token:'tok',
  WebSocketImpl:FakeSocket,onOutput:bytes=>seen.push(new TextDecoder().decode(bytes)),onState:s=>states.push(s)});
 session.open();const ws=FakeSocket.last;ws.onopen();
 assert.equal(JSON.parse(ws.sent[0]).TokenValue,'tok');
 await session.receive(await output(0,PAYLOAD.handshakeRequest,JSON.stringify({RequestedClientActions:[{ActionType:'SessionType'}]})));
 await session.receive(await output(2,PAYLOAD.output,'world'));   // early: buffered
 await session.receive(await output(1,PAYLOAD.handshakeComplete,'{}'));
 await session.receive(await output(3,PAYLOAD.output,'!'));
 await session.receive(await output(3,PAYLOAD.output,'!'));       // duplicate ignored
 assert.deepEqual(seen,['world','!']);assert.ok(states.includes('connected'));
 const types=ws.sent.slice(1).map(m=>decode(m));
 assert.equal(types.filter(m=>m.messageType==='acknowledge').length,5);
 const handshake=types.find(m=>m.payloadType===PAYLOAD.handshakeResponse);assert.ok(handshake);
 const size=types.find(m=>m.payloadType===PAYLOAD.size);assert.deepEqual(JSON.parse(new TextDecoder().decode(size.payload)),{cols:100,rows:28});
 await session.input('ls\r');const last=decode(ws.sent.at(-1));assert.equal(last.messageType,'input_stream_data');assert.equal(new TextDecoder().decode(last.payload),'ls\r');
});

test('session refuses stream URLs outside Session Manager',()=>{
 const session=new SsmSession({streamUrl:'wss://evil.example/x',token:'t',WebSocketImpl:FakeSocket});
 assert.throws(()=>session.open(),/stream URL/);
});

test('terminal screen handles prompts, readline redraws, colors and clear',()=>{
 const s=createScreen();
 write(s,'\x1b[01;32m[ssm-user@ip ~]$\x1b[0m ls\r\nfile.txt\r\n$ ');
 assert.equal(render(s),'[ssm-user@ip ~]$ ls\nfile.txt\n$ ');
 write(s,'abc\b\b\x1b[K');assert.equal(render(s).split('\n').at(-1),'$ a');
 write(s,'\x1b[H\x1b[2J$ ');assert.equal(render(s),'$ ');
 assert.equal(keySequence({key:'c',ctrlKey:true}),'\x03');assert.equal(keySequence({key:'Enter'}),'\r');
 assert.equal(keySequence({key:'ArrowUp'}),'\x1b[A');assert.equal(keySequence({key:'Shift'}),null);
});

test('cost chart draws actual bars only for days that have data and never as zero',async()=>{
 const {document}=parseHTML('<html><body></body></html>');globalThis.document=document;await setLanguage('en',{persist:false});
 const svg=costChart({days:[{date:'2026-11-10',estimated_milliusd:500,actual_milliusd:420},{date:'2026-11-11',estimated_milliusd:500,actual_milliusd:null},
  {date:'2026-11-12',estimated_milliusd:250,actual_milliusd:null}]});
 assert.equal(svg.querySelectorAll('rect').length,1);assert.ok(svg.querySelector('polyline').getAttribute('points').split(' ').length===3);
 delete globalThis.document;
});

test('cloud tools appear only where the backend supports them',async()=>{
 const {document}=parseHTML('<html><body><div></div></body></html>');globalThis.document=document;await setLanguage('en',{persist:false});
 const labels=env=>{const host=document.createElement('div');appendCloudTools(host,env,{});return [...host.querySelectorAll('button')].map(b=>[b.textContent,b.disabled]);};
 assert.deepEqual(labels({template_id:'T01',status:'READY'}),[['Terminal',false],['Change machine type',false],['Daily cost',false]]);
 assert.deepEqual(labels({template_id:'T08',status:'READY'}).map(x=>x[0]),['Terminal · Machine 1','Terminal · Machine 2','Daily cost']);
 assert.deepEqual(labels({template_id:'T09',status:'READY'}),[['Daily cost',false]]);
 assert.deepEqual(labels({template_id:'T05',status:'PROVISIONING'}).slice(0,2).map(x=>x[1]),[true,true]);
 delete globalThis.document;
});
