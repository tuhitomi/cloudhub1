import {test} from 'node:test';
import assert from 'node:assert/strict';
import {verify} from '../scripts/verify_hosting.mjs';

const inventory={frontend:{distribution_domain:'example.cloudfront.net',s3_policy_status:{IsPublic:false},s3_block_public_access:{a:true,b:true,c:true,d:true}},api:{endpoint:'https://api123.execute-api.ap-southeast-1.amazonaws.com'}};
function transport(overrides={}){return async(url,method)=>{
  if(url.startsWith('http:'))return {status:301,headers:{location:url.replace('http:','https:')}};
  if(url.endsWith('__cloudhub_missing_asset_validation__.js'))return {status:overrides.missing||403,headers:{},body:'denied'};
  if(url.endsWith('/templates'))return method==='OPTIONS'?{status:204,headers:{'access-control-allow-origin':overrides.cors||'https://example.cloudfront.net'}}:{status:overrides.auth||401,headers:{},tls:{authorized:overrides.apiTls!==false}};
  if(url.endsWith('/ui-context'))return {status:200,headers:{'cache-control':overrides.cache||'no-store'}};
  return {status:200,body:'CloudHub',headers:{},tls:{authorized:overrides.tls!==false}};
};}
test('public verifier separates current hosting from custom-domain acceptance',async()=>{
  const result=await verify(inventory,null,transport());assert.equal(result.passed,true);assert.equal(result.checks.length,7);
  assert.equal(result.aws_mutations,0);assert.match(result.not_tested[0],/Interactive/);
});
test('missing assets returning index 200 and unauthenticated APIs returning 200 fail',async()=>{
  for(const overrides of [{missing:200},{auth:200},{tls:false},{apiTls:false},{cors:'*'},{cache:'public,max-age=3600'}]){
    const result=await verify(inventory,null,transport(overrides));assert.equal(result.passed,false);
  }
});
test('custom hostname missing blocks without querying a guessed name',async()=>{
  let calls=0;const result=await verify(inventory,{FRONTEND_DOMAIN:'',API_DOMAIN:''},async()=>{calls++;});
  assert.equal(calls,0);assert.equal(result.passed,false);assert.equal(result.mode,'CUSTOM_DOMAIN_NOT_CONFIGURED');
});

function customInventory(){
  const alias=(name,type,target,zone)=>({Name:name+'.',Type:type,AliasTarget:{DNSName:target+'.',HostedZoneId:zone,EvaluateTargetHealth:false}});
  return {...inventory,api:{...inventory.api,id:'api123',custom_domain:{status:'AVAILABLE',security_policy:'TLS_1_2',target:'native-api.execute-api.ap-southeast-1.amazonaws.com',target_zone:'ZAPI',mappings:[{ApiId:'api123',Stage:'$default',ApiMappingKey:''}]}},
    selected_zone:{name:'example.com.',private:false,nameservers:['ns1.example.net','ns2.example.net'],records:[
      alias('app.example.com','A','example.cloudfront.net','Z2FDTNDATAQYW2'),alias('app.example.com','AAAA','example.cloudfront.net','Z2FDTNDATAQYW2'),
      alias('api.example.com','A','native-api.execute-api.ap-southeast-1.amazonaws.com','ZAPI')]}};
}
const customConfig={ROOT_DOMAIN:'example.com',FRONTEND_DOMAIN:'app.example.com',API_DOMAIN:'api.example.com',API_STAGE:'$default',API_MAPPING_KEY:'',DNS_PROVIDER:'route53',IPV6_ENABLED:true};
const resolver={resolveNs:async()=>['ns1.example.net.','ns2.example.net.'],resolve4:async()=>['198.51.100.1'],resolve6:async()=>['2001:db8::1']};
test('custom-domain verifier requires matching API mapping, public delegation and both frontend aliases',async()=>{
  const r=await verify(customInventory(),customConfig,transport({cors:'https://app.example.com'}),resolver);
  assert.equal(r.passed,true);assert.equal(r.aws_mutations,0);assert.equal(r.mode,'CUSTOM_PUBLIC_READ_ONLY');
  assert(r.checks.some(c=>c.name==='alias_aaaa_target_app.example.com'&&c.passed));
});
test('DNS resolving to an IP does not hide wrong alias ownership, missing AAAA, or foreign API mapping',async()=>{
  for(const change of [i=>{i.selected_zone.records[0].AliasTarget.HostedZoneId='ZFOREIGN';},i=>{i.selected_zone.records.splice(1,1);},
                      i=>{i.api.custom_domain.mappings[0].ApiId='foreign';},i=>{i.selected_zone.nameservers=['ns.evil.example'];}]){
    const i=customInventory();change(i);
    const r=await verify(i,customConfig,transport({cors:'https://app.example.com'}),resolver);assert.equal(r.passed,false);
  }
});
