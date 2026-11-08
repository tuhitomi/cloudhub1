import {test} from 'node:test';
import assert from 'node:assert/strict';
import {parseHTML} from 'linkedom';
import {setLanguage} from '../frontend/i18n.js';
import {testListPath,testSummary,createTestDataView} from '../frontend/test-data-view.js';
await setLanguage('en',{persist:false});
test('test-data read paths preserve pagination without adding owner or changing write paths',()=>{
 assert.equal(testListPath('/environments',false),'/environments');
 assert.equal(testListPath('/admin/users?cursor=abc',true),'/admin/users?cursor=abc&include_test=true');
});
test('hidden reports disclose retained resources without claiming cleanup',()=>{
 assert.match(testSummary({hidden_test_count:175,retained_test_report_count:160}),/175/);
 assert.match(testSummary({retained_test_report_count:160}),/costs may continue/);
 assert.equal(testSummary({hidden_test_count:0}),'');
});
test('show control refreshes read data once, syncs controls, and resets when account changes',async()=>{
 const {window}=parseHTML('<body><input type="checkbox" data-include-test><input type="checkbox" data-include-test><p data-test-summary="environment"></p></body>');
 globalThis.document=window.document;let refreshed=0;
 const view=createTestDataView({refresh:async()=>{refreshed++;},notice:()=>assert.fail('unexpected failure')});
 const [one,two]=document.querySelectorAll('input');one.checked=true;one.dispatchEvent(new window.Event('change'));await new Promise(resolve=>setImmediate(resolve));
 assert.equal(refreshed,1);assert.equal(two.checked,true);assert.equal(view.path('/environments'),'/environments?include_test=true');
 view.render('environment',{hidden_test_count:1});assert.match(document.querySelector('p').textContent,/1/);
 view.reset();assert.equal(one.checked,false);assert.equal(view.path('/environments'),'/environments');assert.equal(document.querySelector('p').hidden,true);
});
