/** Public read-only DNS/TLS/HTTP checks. Never creates an account or sends codes. */
import fs from 'node:fs/promises';
import dns from 'node:dns/promises';
import http from 'node:http';
import https from 'node:https';
import {pathToFileURL} from 'node:url';

export function request(url,method='GET',headers={}){
  return new Promise((resolve,reject)=>{
    const u=new URL(url);const mod=u.protocol==='https:'?https:http;
    const req=mod.request(u,{method,headers,rejectUnauthorized:true,timeout:12000},res=>{
      let body='';res.setEncoding('utf8');res.on('data',s=>{if(body.length<262144)body+=s;});
      const tls=u.protocol==='https:'?{authorized:res.socket.authorized,protocol:res.socket.getProtocol(),valid_to:res.socket.getPeerCertificate().valid_to}:null;
      res.on('end',()=>resolve({status:res.statusCode,headers:res.headers,body,tls}));
    });req.on('timeout',()=>req.destroy(new Error('HTTP timeout')));req.on('error',reject);req.end();
  });
}

export async function verify(inventory,config=null,transport=request,resolver=dns){
  const custom=!!config;const checks=[];const blockers=[];
  const run=async(name,fn)=>{try{const value=await fn();checks.push({name,passed:!!value.passed,...value});}catch(e){checks.push({name,passed:false,error:e.code||e.message});}};
  const front=custom?config.FRONTEND_DOMAIN:inventory.frontend.distribution_domain;
  const mapping=custom?config.API_MAPPING_KEY:'';
  const api=custom?'https://'+config.API_DOMAIN+(mapping?'/'+mapping:''):inventory.api.endpoint;
  if(custom&&(!front||!config.API_DOMAIN))return {mode:'CUSTOM_DOMAIN_NOT_CONFIGURED',passed:false,checks:[],blockers:['Registered domain and configured hostnames required'],aws_mutations:0};
  const origin='https://'+front;
  await run('homepage_https_hostname',async()=>{const r=await transport(origin+'/');return {passed:r.status===200&&r.body.includes('CloudHub')&&r.tls?.authorized===true,status:r.status,tls:r.tls};});
  await run('http_redirects_to_same_https_host',async()=>{const r=await transport('http://'+front+'/');const l=new URL(r.headers.location||'http://invalid');return {passed:[301,302,307,308].includes(r.status)&&l.protocol==='https:'&&l.hostname===front,status:r.status};});
  await run('missing_asset_is_not_index_200',async()=>{const r=await transport(origin+'/__cloudhub_missing_asset_validation__.js');return {passed:[403,404].includes(r.status),status:r.status};});
  await run('api_rejects_unauthenticated',async()=>{const r=await transport(api+'/templates');return {passed:[401,403].includes(r.status)&&r.tls?.authorized===true,status:r.status,tls:r.tls};});
  await run('cors_exact_frontend_origin',async()=>{const r=await transport(api+'/templates','OPTIONS',{'Origin':origin,'Access-Control-Request-Method':'GET','Access-Control-Request-Headers':'authorization,content-type,idempotency-key'});return {passed:[200,204].includes(r.status)&&r.headers['access-control-allow-origin']===origin,status:r.status};});
  await run('country_context_not_shared_cached',async()=>{const r=await transport(origin+'/ui-context');return {passed:r.status===200&&/no-store/i.test(r.headers['cache-control']||''),status:r.status};});
  checks.push({name:'s3_private_native_inventory',passed:inventory.frontend.s3_policy_status?.IsPublic===false&&Object.values(inventory.frontend.s3_block_public_access||{}).length===4&&Object.values(inventory.frontend.s3_block_public_access).every(v=>v===true)});
  if(custom){
    const domain=inventory.api.custom_domain;
    checks.push({name:'api_mapping_native_inventory',passed:domain?.status==='AVAILABLE'&&domain.security_policy==='TLS_1_2'&&domain.mappings.some(m=>m.ApiId===inventory.api.id&&m.Stage===config.API_STAGE&&(m.ApiMappingKey||'')===(mapping||''))});
    if(config.DNS_PROVIDER==='route53'){
      const z=inventory.selected_zone;
      await run('public_zone_delegation',async()=>{const actual=(await resolver.resolveNs(z.name)).map(x=>x.toLowerCase().replace(/\.$/,''));return {passed:z.private===false&&actual.length>0&&actual.length===z.nameservers.length&&z.nameservers.every(x=>actual.includes(x.toLowerCase().replace(/\.$/,'')))};});
      for(const [name,target] of [[front,inventory.frontend.distribution_domain],[config.API_DOMAIN,domain?.target],...(config.REDIRECT_DOMAIN?[[config.REDIRECT_DOMAIN,inventory.frontend.distribution_domain]]:[])]){
        const record=z?.records?.find(r=>r.Name.replace(/\.$/,'')===name&&r.Type==='A');
        const zone=name===config.API_DOMAIN?domain?.target_zone:'Z2FDTNDATAQYW2';
        const matches=r=>!!target&&r?.AliasTarget?.DNSName.replace(/\.$/,'')===target.replace(/\.$/,'')&&r.AliasTarget.HostedZoneId===zone&&r.AliasTarget.EvaluateTargetHealth===false;
        checks.push({name:'alias_target_'+name,passed:matches(record)});
        await run('public_a_'+name,async()=>({passed:(await resolver.resolve4(name)).length>0}));
        if(config.IPV6_ENABLED&&name!==config.API_DOMAIN){
          checks.push({name:'alias_aaaa_target_'+name,passed:matches(z?.records?.find(r=>r.Name.replace(/\.$/,'')===name&&r.Type==='AAAA'))});
          await run('public_aaaa_'+name,async()=>({passed:(await resolver.resolve6(name)).length>0}));
        }
      }
    }else{
      for(const [name,target] of [[front,inventory.frontend.distribution_domain],[config.API_DOMAIN,domain?.target]]){
        if(name===config.ROOT_DOMAIN){blockers.push('External apex ALIAS/ANAME requires provider-side target verification');continue;}
        await run('external_cname_'+name,async()=>({passed:!!target&&(await resolver.resolveCname(name)).some(v=>v.replace(/\.$/,'')===target.replace(/\.$/,''))}));
      }
    }
    if(config.REDIRECT_DOMAIN)await run('www_preserves_path_query',async()=>{const path='/docs/path?x=a%2Bb&tag=one&tag=two';const r=await transport('https://'+config.REDIRECT_DOMAIN+path);return {passed:[301,302,307,308].includes(r.status)&&r.headers.location===origin+path};});
  }
  return {recorded_at:new Date().toISOString(),mode:custom?'CUSTOM_PUBLIC_READ_ONLY':'CURRENT_AWS_HOSTING_READ_ONLY',passed:checks.every(v=>v.passed)&&!blockers.length,
    checks,blockers,not_tested:['Interactive signup/email verification/login/logout/password reset on a custom hostname','Actual Region migration or data rollback'],aws_mutations:0,
    scope:'Public DNS/TLS/HTTP and exact native inventory. No credential, account, email or Region cutover mutation.'};
}

async function main(){
  const args=process.argv.slice(2);const value=k=>args[args.indexOf(k)+1];
  if(!args.includes('--inventory')||!args.includes('--out'))throw new Error('--inventory and --out required');
  const inventory=JSON.parse(await fs.readFile(value('--inventory'),'utf8'));
  const config=args.includes('--config')?JSON.parse(await fs.readFile(value('--config'),'utf8')):null;
  const result=await verify(inventory,config);await fs.writeFile(value('--out'),JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify({mode:result.mode,passed:result.passed,checks:result.checks.length,blockers:result.blockers}));
  if(!result.passed)process.exitCode=1;
}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href)await main();
