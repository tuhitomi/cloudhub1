// AWS Systems Manager Session Manager data channel, spoken directly from the browser.
// The backend calls ssm:StartSession and hands back {stream_url, token}; this module
// opens the WebSocket to ssmmessages.<region>.amazonaws.com, performs the agent
// handshake, acknowledges every output message and delivers it in sequence order.
//
// Binary message layout (big endian), as used by the AWS session-manager-plugin:
//   0 HeaderLength u32 (=116) | 4 MessageType char[32] | 36 SchemaVersion u32
//  40 CreatedDate u64 ms | 48 SequenceNumber i64 | 56 Flags u64 | 64 MessageId 16 bytes
//  80 PayloadDigest sha256[32] | 112 PayloadType u32 | 116 PayloadLength u32 | 120 Payload
export const HEADER_LENGTH=116;
export const PAYLOAD={output:1,error:2,size:3,parameter:4,handshakeRequest:5,handshakeResponse:6,handshakeComplete:7};
const CLIENT_VERSION='1.2.0.0';
const encoder=new TextEncoder(),decoder=new TextDecoder();

function writeU64(view,offset,value){const big=BigInt(value);view.setUint32(offset,Number(big>>32n)>>>0);view.setUint32(offset+4,Number(big&0xffffffffn)>>>0);}
function readU64(view,offset){return Number((BigInt(view.getUint32(offset))<<32n)|BigInt(view.getUint32(offset+4)));}

// The plugin stores a UUID as its least significant 8 bytes followed by the most significant 8.
export function uuidToBytes(uuid){const hex=uuid.replace(/-/g,'');if(!/^[0-9a-f]{32}$/i.test(hex))throw Error('Invalid UUID');
 const bytes=new Uint8Array(16),order=hex.slice(16)+hex.slice(0,16);for(let i=0;i<16;i++)bytes[i]=parseInt(order.slice(i*2,i*2+2),16);return bytes;}
export function bytesToUuid(bytes){const hex=[...bytes].map(b=>b.toString(16).padStart(2,'0')).join(''),ordered=hex.slice(16)+hex.slice(0,16);
 return [ordered.slice(0,8),ordered.slice(8,12),ordered.slice(12,16),ordered.slice(16,20),ordered.slice(20)].join('-');}

async function sha256(bytes){return new Uint8Array(await globalThis.crypto.subtle.digest('SHA-256',bytes));}

export async function encode({messageType,sequenceNumber=0,flags=0,messageId=globalThis.crypto.randomUUID(),payloadType=0,payload=new Uint8Array(),createdDate=Date.now()}){
 const body=typeof payload==='string'?encoder.encode(payload):payload;
 const buffer=new ArrayBuffer(120+body.length),view=new DataView(buffer),bytes=new Uint8Array(buffer);
 view.setUint32(0,HEADER_LENGTH);bytes.set(encoder.encode(messageType.padEnd(32,' ').slice(0,32)),4);view.setUint32(36,1);
 writeU64(view,40,createdDate);writeU64(view,48,sequenceNumber);writeU64(view,56,flags);bytes.set(uuidToBytes(messageId),64);
 bytes.set(await sha256(body),80);view.setUint32(112,payloadType);view.setUint32(116,body.length);bytes.set(body,120);return buffer;
}

export function decode(buffer){
 const view=new DataView(buffer),bytes=new Uint8Array(buffer),headerLength=view.getUint32(0);
 if(headerLength<HEADER_LENGTH||buffer.byteLength<headerLength+4)throw Error('Truncated Session Manager message');
 const length=view.getUint32(headerLength);
 return {messageType:decoder.decode(bytes.slice(4,36)).replace(/[\s\0]+$/,''),schemaVersion:view.getUint32(36),createdDate:readU64(view,40),
  sequenceNumber:readU64(view,48),flags:readU64(view,56),messageId:bytesToUuid(bytes.slice(64,80)),payloadType:view.getUint32(112),
  payload:bytes.slice(headerLength+4,headerLength+4+length)};
}

export function handshakeResponse(request){
 // Only an interactive shell is supported; KMS-encrypted sessions need the AWS CLI plugin.
 const actions=(request.RequestedClientActions||[]).map(action=>action.ActionType==='SessionType'
  ?{ActionType:action.ActionType,ActionStatus:1}:{ActionType:action.ActionType,ActionStatus:2,Error:'Unsupported by the CloudHub browser terminal'});
 return {ClientVersion:CLIENT_VERSION,ProcessedClientActions:actions,Errors:[]};
}

export class SsmSession{
 constructor({streamUrl,token,onOutput=()=>{},onState=()=>{},WebSocketImpl=globalThis.WebSocket,size={cols:100,rows:28}}){
  Object.assign(this,{streamUrl,token,onOutput,onState,WebSocketImpl,size});this.expected=0;this.outgoing=0;this.pending=new Map();this.ready=false;
 }
 open(){
  if(!/^wss:\/\/ssmmessages\.[a-z0-9-]+\.amazonaws\.com(\.cn)?\//.test(this.streamUrl))throw Error('Unexpected Session Manager stream URL');
  const ws=this.ws=new this.WebSocketImpl(this.streamUrl);ws.binaryType='arraybuffer';this.onState('connecting');
  ws.onopen=()=>ws.send(JSON.stringify({MessageSchemaVersion:'1.0',RequestId:globalThis.crypto.randomUUID(),TokenValue:this.token,ClientId:globalThis.crypto.randomUUID(),ClientVersion:CLIENT_VERSION}));
  ws.onmessage=event=>{if(typeof event.data!=='string')this.receive(event.data).catch(error=>this.onState('error',error.message));};
  ws.onerror=()=>this.onState('error','WebSocket error');
  ws.onclose=()=>{this.ready=false;this.onState('closed');};
 }
 async receive(buffer){
  const message=decode(buffer);
  if(message.messageType==='channel_closed'){this.onState('closed');this.ws.close();return;}
  if(message.messageType!=='output_stream_data')return;
  await this.ack(message);
  if(message.sequenceNumber<this.expected||this.pending.has(message.sequenceNumber))return;
  this.pending.set(message.sequenceNumber,message);
  while(this.pending.has(this.expected)){const next=this.pending.get(this.expected);this.pending.delete(this.expected);this.expected++;await this.handle(next);}
 }
 async handle(message){
  if(message.payloadType===PAYLOAD.handshakeRequest){await this.send(PAYLOAD.handshakeResponse,JSON.stringify(handshakeResponse(JSON.parse(decoder.decode(message.payload)))));return;}
  if(message.payloadType===PAYLOAD.handshakeComplete){await this.connected();return;}
  if(message.payloadType===PAYLOAD.output||message.payloadType===PAYLOAD.error){if(!this.ready)await this.connected();this.onOutput(message.payload);}
 }
 async connected(){if(this.ready)return;this.ready=true;this.onState('connected');await this.resize(this.size.cols,this.size.rows);}
 async ack(message){
  const payload=JSON.stringify({AcknowledgedMessageType:message.messageType,AcknowledgedMessageId:message.messageId,AcknowledgedMessageSequenceNumber:message.sequenceNumber,IsSequentialMessage:true});
  this.ws.send(await encode({messageType:'acknowledge',flags:3,payload}));
 }
 async send(payloadType,payload){
  if(this.ws?.readyState!==1)return;
  this.ws.send(await encode({messageType:'input_stream_data',sequenceNumber:this.outgoing++,payloadType,payload}));
 }
 input(text){return this.ready?this.send(PAYLOAD.output,text):Promise.resolve();}
 resize(cols,rows){this.size={cols,rows};return this.send(PAYLOAD.size,JSON.stringify({cols,rows}));}
 close(){try{this.ws?.close();}catch{}}
}
