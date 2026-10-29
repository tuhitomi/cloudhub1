import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import {parseHTML} from 'linkedom';
import {countryLanguage,resolveLanguage,setLanguage,initializeLanguage,accountLanguage,languageState,t,installLanguageUI,disposeLanguageUI,money,date} from '../frontend/i18n.js';
const codes=['en','vi','ja','ko','zh-Hans','fr','de','es'],packs={};
for(const code of codes)packs[code]=JSON.parse(await fs.readFile(new URL('../frontend/locales/'+code+'.json',import.meta.url),'utf8'));
const loader=async code=>packs[code];
function storage(initial={}){const values=new Map(Object.entries(initial));globalThis.localStorage={getItem:k=>values.get(k)??null,setItem:(k,v)=>values.set(k,v)};return values;}
const fetchPacks=async url=>({ok:true,json:async()=>packs[new URL(url).pathname.split('/').pop().replace('.json','')]});
test('all eight packs contain every English key and preserve interpolation parameters',()=>{
 const keys=Object.keys(packs.en).sort();assert.ok(keys.length>=610);
 for(const code of codes){assert.deepEqual(Object.keys(packs[code]).sort(),keys);for(const key of keys){assert.equal(typeof packs[code][key],'string');assert.ok(packs[code][key].trim());assert.deepEqual((packs[code][key].match(/\{p\d+\}/g)||[]).sort(),(packs.en[key].match(/\{p\d+\}/g)||[]).sort());}}
});
test('country map ignores browser language and uses English for unknown or missing country',async()=>{
 for(const [country,lang]of Object.entries({VN:'vi',JP:'ja',KR:'ko',CN:'zh-Hans',FR:'fr',DE:'de',ES:'es',US:'en',XX:'en'}))assert.equal(countryLanguage(country),lang);
 assert.equal(countryLanguage(null),'en');assert.equal(resolveLanguage('ko','vi','JP'),'ko');assert.equal(resolveLanguage(null,'fr','VN'),'fr');assert.equal(resolveLanguage(null,null,'JP'),'ja');
 disposeLanguageUI();storage();globalThis.fetch=fetchPacks;Object.defineProperty(globalThis,'navigator',{value:{language:'vi-VN'},configurable:true});await initializeLanguage({context:async()=>({country_code:'DE'})});assert.equal(languageState().locale,'de');
});
test('failed locale download and missing keys fall back to readable English, never keys',async()=>{
 await setLanguage('ja',{persist:false,loader:async()=>{throw Error('offline');}});assert.equal(t('language.label'),'Language');assert.doesNotMatch(t('nonexistent.key'),/nonexistent\.key/);
 await setLanguage('fr',{persist:false,loader:async()=>({'language.label':'Langue'})});assert.equal(t('language.label'),'Langue');assert.equal(t('template.T01.name'),'Linux machine');
});
test('manual choice survives IP changes and login; auto can be explicitly selected again',async()=>{
 disposeLanguageUI();const local=storage({'cloudhub.language':'ko'});globalThis.fetch=fetchPacks;const saved=[];
 await initializeLanguage({context:async()=>({country_code:'VN'})});assert.equal(languageState().locale,'ko');await accountLanguage({language_preference:'ja'},async value=>saved.push(value));assert.equal(languageState().locale,'ko');assert.equal(saved.at(-1),'ko');
 await setLanguage('es',{loader});assert.equal(local.get('cloudhub.language'),'es');assert.equal(saved.at(-1),'es');
 await initializeLanguage({context:async()=>({country_code:'JP'})});assert.equal(languageState().locale,'es');await setLanguage('auto',{loader});assert.equal(languageState().locale,'ja');assert.equal(local.get('cloudhub.language'),'auto');
});
test('account choice is used without a browser choice; lookup failure chooses English',async()=>{
 disposeLanguageUI();storage();globalThis.fetch=fetchPacks;await initializeLanguage({context:async()=>{throw Error('offline');}});assert.equal(languageState().locale,'en');await accountLanguage({language_preference:'zh-Hans'},async()=>{});assert.equal(languageState().locale,'zh-Hans');
});
test('switching language preserves form values, selected Region, identifiers and technical logs',async()=>{
 disposeLanguageUI();storage();const {document,window}=parseHTML('<html><body><label data-i18n="language.label">Language</label><select id="language-select"></select><input id="budget" value="12.345"><select id="region"><option selected value="ap-northeast-1">ap-northeast-1</option></select><pre>ERROR source: env-save</pre><span translate="no">env-save-resource</span></body></html>');globalThis.document=document;globalThis.MutationObserver=window.MutationObserver;Object.defineProperty(window.HTMLSelectElement.prototype,'value',{configurable:true,get(){return this._testValue??this.querySelector('option[selected]')?.value??this.querySelector('option')?.value??'';},set(value){this._testValue=String(value);}});installLanguageUI(document);
 await setLanguage('de',{persist:false,loader});assert.equal(document.querySelector('#budget').value,'12.345');assert.equal(document.querySelector('#region').value,'ap-northeast-1');assert.equal(document.querySelector('pre').textContent,'ERROR source: env-save');assert.equal(document.querySelector('[translate="no"]').textContent,'env-save-resource');assert.equal(document.querySelector('label').textContent,'Sprache');assert.ok(document.querySelector('option[value="auto"]'));disposeLanguageUI();
});
test('numbers and dates use locale while currency and schedule timezone remain explicit',async()=>{
 await setLanguage('de',{persist:false,loader});assert.match(money(1234567),/1\.234,567/);assert.match(money(1234567),/USD/);assert.match(date(1700000000),/Asia\/Bangkok, UTC\+07:00/);await setLanguage('en',{persist:false});assert.match(money(1234567),/USD/);
});


test('new product messages cover eight locales and preserve named placeholders',async()=>{
 const fs=await import('node:fs/promises');const codes=['en','vi','ja','ko','zh-Hans','fr','de','es'];const packs={};
 for(const code of codes)packs[code]=JSON.parse(await fs.readFile(new URL('../frontend/locales/'+code+'.json',import.meta.url),'utf8'));
 assert.equal(Object.keys(packs).length,8);
 for(const pack of Object.values(packs))for(const [key,text]of Object.entries(packs.en)){
  assert.equal(typeof pack[key],'string');assert.ok(pack[key].trim());
  assert.deepEqual((pack[key].match(/\{[A-Za-z0-9_]+\}/g)||[]).sort(),(text.match(/\{[A-Za-z0-9_]+\}/g)||[]).sort());
 }
});
