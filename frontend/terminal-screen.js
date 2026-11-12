// Minimal line-oriented terminal: enough for a shell (prompt, output, readline
// editing, clear). Full-screen programs (vim, top) need the AWS CLI session plugin.
const MAX_LINES=2000;
const TOKEN=/\x1b\[([0-9;?]*)([ -\/]*)([@-~])|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[()][A-Za-z0-9]|\x1b[=>78DMEc]|[^\x1b]+|\x1b/g;

export function createScreen(){return {lines:[''],cursor:0};}

function text(screen,chunk){
 let line=screen.lines[screen.lines.length-1],cursor=screen.cursor;
 for(const char of chunk){
  if(char==='\n'){screen.lines[screen.lines.length-1]=line;screen.lines.push('');line='';cursor=0;}
  else if(char==='\r')cursor=0;
  else if(char==='\b')cursor=Math.max(0,cursor-1);
  else if(char<' '&&char!=='\t')continue;
  else{line=line.padEnd(cursor,' ');line=line.slice(0,cursor)+char+line.slice(cursor+1);cursor++;}
 }
 screen.lines[screen.lines.length-1]=line;screen.cursor=cursor;
}

function csi(screen,params,final){
 const n=Math.max(1,parseInt(params||'1',10)||1),last=screen.lines.length-1,line=screen.lines[last];
 if(final==='K'){
  if(params===''||params==='0')screen.lines[last]=line.slice(0,screen.cursor);
  else if(params==='1')screen.lines[last]=' '.repeat(screen.cursor)+line.slice(screen.cursor);
  else screen.lines[last]='';
 }
 else if(final==='C')screen.cursor+=n;
 else if(final==='D')screen.cursor=Math.max(0,screen.cursor-n);
 else if(final==='P')screen.lines[last]=line.slice(0,screen.cursor)+line.slice(screen.cursor+n);
 else if(final==='J'&&(params==='2'||params==='3')){screen.lines=[''];screen.cursor=0;}
 else if(final==='H'&&!params&&screen.lines.length===1&&!screen.lines[0])screen.cursor=0;
}

export function write(screen,chunk){
 for(const match of chunk.matchAll(TOKEN)){
  if(match[3])csi(screen,match[1],match[3]);
  else if(match[0]==='\x1bc'){screen.lines=[''];screen.cursor=0;}
  else if(match[0][0]!=='\x1b')text(screen,match[0]);
 }
 if(screen.lines.length>MAX_LINES)screen.lines.splice(0,screen.lines.length-MAX_LINES);
 return screen;
}

export const render=screen=>screen.lines.join('\n');

const KEYS={Enter:'\r',Backspace:'\x7f',Tab:'\t',Escape:'\x1b',ArrowUp:'\x1b[A',ArrowDown:'\x1b[B',ArrowRight:'\x1b[C',ArrowLeft:'\x1b[D',
 Home:'\x1b[H',End:'\x1b[F',Delete:'\x1b[3~',PageUp:'\x1b[5~',PageDown:'\x1b[6~'};

export function keySequence(event){
 if(event.metaKey)return null;
 if(event.ctrlKey&&!event.altKey&&/^[a-z]$/i.test(event.key))return String.fromCharCode(event.key.toUpperCase().charCodeAt(0)-64);
 if(KEYS[event.key])return KEYS[event.key];
 if(event.key.length===1&&!event.ctrlKey)return event.key;
 return null;
}
