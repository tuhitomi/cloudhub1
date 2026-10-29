// Synthetic DOM checks only: these do not create resources or prove AWS readiness.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {parseHTML} from 'linkedom';
import {setLanguage,t} from '../frontend/i18n.js';
import {createCatalogView} from '../frontend/catalog-view.js';
import {renderQuotaVisual} from '../frontend/quota-view.js';
const rows=Array.from({length:9},(_,i)=>({template_id:'T0'+(i+1),services:i===6?['S3']:['AWS'],create_enabled:i!==3}));
function dom(){const {window}=parseHTML('<html><body><div id="catalog-tools"></div><div id="catalog"></div><div id="quota-visual"></div><details id="quota-explanation"></details></body></html>');globalThis.document=window.document;return {window,$:s=>document.querySelector(s)};}
await setLanguage('vi',{persist:false});
test('filters and accent-insensitive search combine without changing backend availability',()=>{
 const {window,$}=dom(),selections=[];const view=createCatalogView({onSelect:r=>selections.push(r.template_id)});
 try{
  view.update([...rows,{template_id:'T10'}],{guest:false});assert.equal($('#catalog').children.length,9);
  $('[data-group="compute"]').click();assert.deepEqual(view.snapshot().visible,['T01','T05','T08']);
  const search=$('#catalog-search');search.value='O dia';search.dispatchEvent(new window.Event('input'));assert.deepEqual(view.snapshot().visible,['T08']);
  view.update(rows,{guest:false});assert.equal($('#catalog-search'),search);assert.deepEqual(view.snapshot().visible,['T08']);
  search.value='';search.dispatchEvent(new window.Event('input'));$('[data-group="all"]').click();
  const blocked=$('[data-template="T04"] .catalog-select');assert.equal(blocked.disabled,true);blocked.click();assert.deepEqual(selections,[]);
  $('[data-template="T01"] .catalog-select').click();assert.deepEqual(selections,['T01']);
 }finally{view.dispose();}
});
test('guest cards offer sign-in and read-only preview; API text cannot inject markup',()=>{
 const {$}=dom(),calls=[];const view=createCatalogView({onSelect:(r,c)=>calls.push(['select',r.template_id,c.guest]),onPreview:r=>calls.push(['preview',r.template_id])});
 try{view.update([{...rows[0],services:['<img src=x onerror=alert(1)>']}]);
  $('.catalog-select').click();$('.catalog-preview').click();assert.deepEqual(calls,[['select','T01',true],['preview','T01']]);
  assert.equal(document.querySelector('img'),null);assert.equal(document.querySelector('.catalog-availability'),null);
 }finally{view.dispose();}
});
test('locale changes retain query/filter and focused search node, including empty results',async()=>{
 const {window,$}=dom(),view=createCatalogView();try{
  view.update(rows);$('[data-group="web"]').click();const search=$('#catalog-search');search.value='T02';search.dispatchEvent(new window.Event('input'));
  await setLanguage('de',{persist:false});assert.equal($('#catalog-search'),search);assert.deepEqual(view.snapshot(),{group:'web',query:'T02',visible:['T02']});
  assert.equal($('[data-group="web"]').getAttribute('aria-pressed'),'true');search.value='unmatched';search.dispatchEvent(new window.Event('input'));assert.equal($('#catalog article'),null);assert.ok($('.empty-state-message').textContent.length>0);
 }finally{view.dispose();await setLanguage('vi',{persist:false});}
});

test('header search keeps its input and query during refresh, filtering and locale changes',async()=>{
 const {window,$}=dom();const top=document.createElement('div');top.id='topbar-search';document.body.prepend(top);
 const view=createCatalogView();try{view.update(rows);const search=$('#catalog-search');assert.equal(search.closest('#topbar-search'),top);
  search.value='S3';search.dispatchEvent(new window.Event('input'));assert.deepEqual(view.snapshot().visible,['T07']);
  view.update(rows,{guest:false});await setLanguage('en',{persist:false});assert.equal($('#catalog-search'),search);assert.equal(search.value,'S3');assert.deepEqual(view.snapshot().visible,['T07']);
  assert.equal(document.querySelectorAll('#catalog-search').length,1);assert.equal($('#catalog .catalog-specs li').textContent,'S3');
 }finally{view.dispose();await setLanguage('vi',{persist:false});}
});

test('guest quota offers sign-in with policy details and account transition hides guest affordances',()=>{
 const {$}=dom();for(const id of ['quota-guest','quota-signin']){const node=document.createElement(id==='quota-signin'?'button':'p');node.id=id;document.body.append(node);}
 renderQuotaVisual(null);assert.equal($('#quota-signin').hidden,false);assert.equal($('#quota-explanation').open,false);
 renderQuotaVisual({active:0,max_active:2,remaining_milliusd:2000,user_budget_milliusd:10000});assert.equal($('#quota-signin').hidden,true);assert.equal($('#quota-guest').hidden,true);
 renderQuotaVisual(null);assert.equal($('#quota-signin').hidden,false);assert.equal($('#quota-visual').hidden,true);
});
test('quota meters use API values, preserve expanded details and never invent unknown budgets',()=>{
 const {$}=dom();renderQuotaVisual(null);assert.equal($('#quota-visual').hidden,true);assert.equal($('#quota-explanation').open,false);
 renderQuotaVisual({active:1,max_active:2,remaining_milliusd:2000,user_budget_milliusd:10000});
 assert.equal($('#quota-explanation').open,false);assert.deepEqual([...document.querySelectorAll('[role="progressbar"]')].map(n=>n.getAttribute('aria-valuenow')),['1','2000']);
 assert.match($('#quota-visual').textContent,/2,000/);assert.match($('#quota-visual').textContent,/không phải.*AWS/i);
 $('#quota-explanation').open=true;renderQuotaVisual({active:1,max_active:2,remaining_milliusd:null,user_budget_milliusd:null});assert.equal($('#quota-explanation').open,true);
 assert.equal(document.querySelectorAll('[role="progressbar"]').length,1);assert.ok($('#quota-visual').textContent.includes(t('common.unknown')));assert.doesNotMatch($('#quota-visual').textContent,/0,000/);
 renderQuotaVisual(null);assert.equal($('#quota-visual').children.length,0);
});
