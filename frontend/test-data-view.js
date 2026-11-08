import {t,number} from './i18n.js';
export function testListPath(path,include){return include?path+(path.includes('?')?'&':'?')+'include_test=true':path;}
export function testSummary(value){
 const parts=[];
 if(value?.hidden_test_count>0)parts.push(t('testData.hidden',{count:number(value.hidden_test_count)}));
 if(value?.retained_test_report_count>0)parts.push(t('testData.retained',{count:number(value.retained_test_report_count)}));
 return parts.join(' ');
}
export function createTestDataView({refresh,notice}){
 let include=false,busy=false;
 const controls=()=>[...document.querySelectorAll('[data-include-test]')];
 function sync(){for(const control of controls()){control.checked=include;control.disabled=busy;}}
 async function change(event){
  if(busy)return;const previous=include;include=event.target.checked;busy=true;sync();
  try{await refresh();}catch(error){include=previous;notice(error.message);}finally{busy=false;sync();}
 }
 for(const control of controls())control.addEventListener('change',change);
 sync();
 return {path:path=>testListPath(path,include),render:(scope,value)=>{
  for(const node of document.querySelectorAll('[data-test-summary="'+scope+'"]')){node.textContent=testSummary(value);node.hidden=!node.textContent;}
 },reset:()=>{include=false;busy=false;sync();for(const node of document.querySelectorAll('[data-test-summary]')){node.textContent='';node.hidden=true;}}};
}
