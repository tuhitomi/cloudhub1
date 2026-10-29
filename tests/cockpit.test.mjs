import {test} from 'node:test';
import assert from 'node:assert/strict';
import {parseHTML} from 'linkedom';
import {setLanguage,t} from '../frontend/i18n.js';
import {operationSteps,appendOperationTracker,appendEnvironmentClock,updateClocks,renderRecordResult,createFileDropZone,renderReleaseStudio} from '../frontend/cockpit.js';
await setLanguage('en',{persist:false});
function dom(){const {window}=parseHTML('<html><body><main></main><input type="file"><div id="drop"></div></body></html>');globalThis.document=window.document;return {window,host:document.querySelector('main')};}
test('tracker derives milestones from durable phases; failure, unknown and cancellation never imply success',()=>{
 assert.deepEqual(operationSteps({action:'create',phase:'WAIT_CREATE',status:'RUNNING'}).map(s=>s.state),['current','pending','pending']);
 assert.deepEqual(operationSteps({action:'restore',phase:'READINESS',status:'FAILED'}).map(s=>s.state),['complete','failed','pending']);
 assert.deepEqual(operationSteps({action:'create',phase:'WAIT_CREATE',status:'CANCELLED'}).map(s=>s.state),['cancelled','pending','pending']);
 assert.deepEqual(operationSteps({action:'create',phase:'UNRECOGNIZED',status:'RUNNING'}),[]);
 const {host}=dom();appendOperationTracker(host,{action:'create',phase:'SCHEDULE',status:'RUNNING',created_at:100,updated_at:110});
 assert.equal(host.querySelectorAll('[aria-current=step]').length,1);assert.match(host.textContent,/not yet estimated/);assert.doesNotMatch(host.textContent,/90s|100%|DNS/);
 updateClocks(host,120000);assert.match(host.querySelector('.operation-elapsed').textContent,/00:00:20/);
 host.replaceChildren();appendOperationTracker(host,{action:'create',phase:'WAIT_CREATE',status:'RUNNING'});assert.match(host.textContent,/Last update: Unknown/);assert.doesNotMatch(host.textContent,/Not started/);
});
test('continuous has no fake deadline; expired deadline waits for actual backend result',()=>{
 const {host}=dom();appendEnvironmentClock(host,{status:'READY',deadline:500,operating_policy:{mode:'CONTINUOUS'}});assert.equal(host.querySelector('[data-deadline]'),null);
 host.replaceChildren();appendEnvironmentClock(host,{status:'READY',deadline:500});updateClocks(host,501000);assert.equal(host.textContent,t('experience.deadlineReached'));
});
test('record table preserves actual empty/unknown distinction and escapes untrusted data',()=>{
 const {host}=dom();renderRecordResult(host,{items:[{record_id:'row-1',text:'<img src=x onerror=alert(1)>'}]});
 assert.equal(host.querySelector('img'),null);assert.match(host.querySelector('tbody').textContent,/<img/);assert.equal(host.querySelectorAll('th[scope=col]').length,2);
 renderRecordResult(host,{items:[]});assert.match(host.textContent,/Returned records: 0/);
 renderRecordResult(host,{ready:true});assert.equal(host.querySelector('table'),null);assert.match(host.textContent,/No record list/);
});
test('file drop only selects one file; blocked and multi-file drops never upload',()=>{
 const {window}=dom(),zone=document.querySelector('#drop'),input=document.querySelector('input'),chosen=[],errors=[];let allowed=true;
 createFileDropZone({zone,input,allowed:()=>allowed,onSelect:f=>chosen.push(f),onError:m=>errors.push(m)});
 const drop=files=>{const e=new window.Event('drop',{cancelable:true});e.dataTransfer={files};zone.dispatchEvent(e);};
 drop([{name:'index.html'}]);assert.equal(chosen.length,1);drop([{name:'a'},{name:'b'}]);assert.equal(chosen.length,1);assert.equal(errors.length,1);
 allowed=false;drop([{name:'denied'}]);assert.equal(chosen.length,1);assert.equal(zone.getAttribute('role'),'button');
});
test('release studio uses returned version identifiers and requires a draft for writes',()=>{
 const {host}=dom();renderReleaseStudio(host,{active_release_id:'release-A',previous_release_id:'release-B',write_enabled:false});
 assert.match(host.textContent,/release-A/);assert.match(host.textContent,/release-B/);assert.match(host.textContent,/Prepare a draft/);assert.equal(host.querySelector('button'),null);
});
