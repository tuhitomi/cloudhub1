import {test} from 'node:test';
import assert from 'node:assert/strict';
import {parseHTML} from 'linkedom';
import {setLanguage} from '../frontend/i18n.js';
import {matchesAdminEnvironment,appendOwner,createAccountSearch} from '../frontend/admin-directory-view.js';
await setLanguage('en',{persist:false});
test('environment search uses owner email and retains the original ID as fallback',()=>{
 assert.equal(matchesAdminEnvironment({owner_email:'User@Sample.test',owner_id:'subject-123'},' user@sample '),true);
 assert.equal(matchesAdminEnvironment({owner_id:'legacy-123'},'123'),true);
 const {window}=parseHTML('<html><body><article></article></body></html>');globalThis.document=window.document;
 const el=(tag,text,cls)=>{const n=document.createElement(tag);n.textContent=text||'';if(cls)n.className=cls;return n;};
 appendOwner(document.querySelector('article'),{owner_email:'<script>@sample.test',owner_id:'subject'},el);
 assert.equal(document.querySelectorAll('script').length,0);assert.match(document.body.textContent,/subject/);
});
test('late account search responses never overwrite newer queries and pagination resets',async()=>{
 const {window}=parseHTML('<body><input id="admin-user-search"><p id="admin-user-search-status"></p><button id="admin-more-users"></button></body>');globalThis.document=window.document;
 let resolveOld,paths=[],shown=[];const first=new Promise(resolve=>{resolveOld=resolve;});
 const search=createAccountSearch({isAdmin:()=>true,path:p=>p,onItems:v=>{shown=v;},onSummary:()=>{},onError:e=>assert.fail(e),api:p=>{paths.push(p);return paths.length===1?first:Promise.resolve({items:[{owner_id:'new',email:'new@sample.test'}],next_cursor:null});}});
 document.querySelector('input').value='old';const old=search.load();document.querySelector('input').value='new';await search.load();
 resolveOld({items:[{owner_id:'old'}],next_cursor:'old-page'});await old;
 assert.equal(shown[0].owner_id,'new');assert.equal(document.querySelector('button').hidden,true);assert.match(paths[1],/q=new/);assert.doesNotMatch(paths[1],/cursor/);
 search.reset();assert.equal(document.querySelector('input').value,'');assert.deepEqual(shown,[]);
});
test('partial zero matches offers continuation and read-only load-more preserves query',async()=>{
 const {window}=parseHTML('<body><input id="admin-user-search"><p id="admin-user-search-status"></p><button id="admin-more-users"></button></body>');globalThis.document=window.document;
 let paths=[];const search=createAccountSearch({isAdmin:()=>true,path:p=>p+'&include_test=true',onItems:()=>{},onSummary:()=>{},onError:e=>assert.fail(e),api:async p=>{paths.push(p);return {items:[],next_cursor:paths.length===1?'p2':null};}});
 document.querySelector('input').value='member@sample';await search.load();assert.equal(document.querySelector('button').hidden,false);assert.match(document.querySelector('p').textContent,/More pages/);
 await search.load(true);assert.match(paths[1],/cursor=p2/);assert.match(paths[1],/q=member%40sample/);search.reset();
});
