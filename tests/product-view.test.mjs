import {test} from 'node:test';import assert from 'node:assert/strict';import {parseHTML} from 'linkedom';
import {appendCleanupReport,backupAvailability,appendCostSummary,restoreReview} from '../frontend/product-view.js';

test('restore confirmation presents source, original Region, hardware and approved app without raw metadata',()=>{
 const text=restoreReview({template_id:'T03',recovery_point:'rp-restore',created_at:1792403767,region:'ap-southeast-1',configuration:{db_gib:20},application:{release_id:'content-site-2',internal:'not-for-display'},internal:'not-for-display'});
 assert.match(text,/rp-restore/);assert.match(text,/ap-southeast-1/);assert.match(text,/PostgreSQL 20 GiB/);assert.match(text,/content-site-2/);assert.match(text,/Asia\/Bangkok/);assert.doesNotMatch(text,/not-for-display|db_gib|\{/);
});
test('retirement report preserves unknown and residual scope instead of claiming clean',()=>{
 const {window}=parseHTML('<html><body><main></main></body></html>');globalThis.window=window;globalThis.document=window.document;const host=document.querySelector('main');
 appendCleanupReport(host,{checked_at:1000,deleted:[{type:'EC2',id:'i-1'}],unknown:[{type:'S3',id:'bucket'}],retained:[{type:'Snapshot',id:'snap'}],billable:[{type:'Snapshot',id:'snap'}]});
 assert.equal(host.querySelectorAll('tr[data-result="unknown"]').length,1);assert.equal(host.querySelectorAll('tr[data-result="retained"]').length,1);assert.ok(host.querySelector('details details pre'));assert.equal(host.querySelectorAll('td').length,12);
});
test('deleted backups cannot act and old retention timestamp cannot revive them',()=>{
 const result=backupAvailability({status:'DELETED',retain_until:9999999999},1000);assert.equal(result.restore.allowed,false);assert.equal(result.restore.reason,'DELETED');assert.equal(result.export.allowed,false);assert.equal(result.delete.allowed,false);
});
test('partially failed deletions explain why data actions are blocked',()=>{
 const result=backupAvailability({status:'DELETE_FAILED',retain_until:9999999999},1000);assert.equal(result.restore.allowed,false);assert.equal(result.restore.reason,'DELETE_FAILED');assert.equal(result.export.allowed,false);assert.equal(result.export.reason,'DELETE_FAILED');assert.equal(result.delete.allowed,true);
});
test('unknown line prices are omitted from the numeric subtotal presentation',()=>{
 const {window}=parseHTML('<html><body><main></main></body></html>');globalThis.window=window;globalThis.document=window.document;const host=document.querySelector('main');appendCostSummary(host,{lines:{compute:null,storage:'0.00041'},total_milliusd:null,known_subtotal_milliusd:1,known_subtotal_usd:'0.000492'});assert.equal(host.querySelectorAll('dt').length,1);assert.equal(host.querySelector('dd').textContent.includes('NaN'),false);
});
