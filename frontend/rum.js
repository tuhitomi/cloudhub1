// Real-user monitoring (Amazon CloudWatch RUM). Optional: does nothing unless the
// deployment publishes rum-config.json next to index.html (scripts/experience_infra.py).
// The client is loaded after the page is idle so it never delays the first render.
const FIELDS=['appMonitorId','identityPoolId','guestRoleArn','region'];

export function validRumConfig(value){
 return !!value&&FIELDS.every(key=>typeof value[key]==='string'&&value[key].length>0)&&/^[a-z]{2}-[a-z]+-\d$/.test(value.region)
  &&(value.sessionSampleRate==null||(typeof value.sessionSampleRate==='number'&&value.sessionSampleRate>=0&&value.sessionSampleRate<=1));
}

export function rumOptions(value){
 return {sessionSampleRate:value.sessionSampleRate??1,identityPoolId:value.identityPoolId,guestRoleArn:value.guestRoleArn,
  endpoint:`https://dataplane.rum.${value.region}.amazonaws.com`,telemetries:['performance','errors'],allowCookies:false,enableXRay:false};
}

export async function startRum({win=globalThis.window,fetcher=(...args)=>fetch(...args),src='vendor/aws-rum-web/cwr.js'}={}){
 if(!win?.document||win.AwsRumClient)return false;
 let value;
 try{const response=await fetcher('rum-config.json',{cache:'no-store',credentials:'omit'});if(!response.ok)return false;value=await response.json();}catch{return false;}
 if(!validRumConfig(value))return false;
 // Same bootstrap as the snippet the CloudWatch console generates; cwr.js drains the queue.
 const client=win.AwsRumClient={q:[],n:'cwr',i:value.appMonitorId,v:'1.0.0',r:value.region,c:rumOptions(value)};
 win.cwr=(c,p)=>{client.q.push({c,p});};
 const script=win.document.createElement('script');script.async=true;script.src=src;win.document.head.append(script);
 return true;
}

if(globalThis.window?.document){
 const idle=globalThis.requestIdleCallback||(callback=>setTimeout(callback,1500));
 globalThis.addEventListener?.('load',()=>idle(()=>{startRum();}),{once:true});
}
