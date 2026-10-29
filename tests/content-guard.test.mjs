import {test} from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
const rid='release-'+'a'.repeat(24),draft='release-'+'b'.repeat(24);
const code=execFileSync(process.env.CLOUDHUB_TEST_PYTHON||'python',['-B','-c',`import sys;sys.path.insert(0,'backend');from cloudhub.content_routing import routing_code;print(routing_code('${rid}',['initial','${rid}']))`],{cwd:new URL('..',import.meta.url),encoding:'utf8'});
const handler=new Function('event',code+';return handler(event);');
const request=uri=>handler({request:{uri}});
test('guard hides drafts/internal paths and refuses unversioned assets',()=>{
 for(const uri of ['/.cloudhub/releases/draft/index.html','/%2ecloudhub/releases/draft/index.html','/%252ecloudhub/releases/draft/index.html','/%25252ecloudhub/releases/draft/index.html','/x/../.cloudhub/releases/draft/index.html','/app.js','/_cloudhub_site/'+draft+'/index.html','/_cloudhub_site/'+rid+'/../index.html','/_cloudhub_site/'+rid+'/.cloudhub/ready.txt'])assert.equal(request(uri).statusCode,403,uri);
 assert.equal(request('/.cloudhub/ready.txt').uri,'/.cloudhub/ready.txt');
});
test('public root redirects without caching and preserves query; old HTML retains old assets',()=>{
 const response=handler({request:{uri:'/',querystring:{q:{value:'a b'}}}});
 assert.equal(response.statusCode,302);assert.equal(response.headers.location.value,'/_cloudhub_site/'+rid+'/index.html?q=a%20b');
 assert.match(response.headers['cache-control'].value,/no-store/);
 assert.equal(request('/_cloudhub_site/initial/app.js').uri,'/app.js');
 assert.equal(request('/_cloudhub_site/'+rid+'/app.js').uri,'/.cloudhub/releases/'+rid+'/app.js');
});
