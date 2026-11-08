import {test} from 'node:test';
import assert from 'node:assert/strict';
import {parseHTML} from 'linkedom';
import {setLanguage,t,money} from '../frontend/i18n.js';
import {budgetDecision,renderQuotaVisual} from '../frontend/quota-view.js';
import {errorText} from '../frontend/error-text.js';
import {createCreationFlow} from '../frontend/create-flow.js';
await setLanguage('en',{persist:false});
const limits=()=>({active:0,max_active:2,remaining_environments:2,user_budget_milliusd:10000,user_remaining_milliusd:10000,remaining_milliusd:123,global_remaining_milliusd:123,global_remaining_environments:4,
 wallet:{granted_milliusd:10000,balance_milliusd:10000,committed_milliusd:0},platform_budget:{remaining_milliusd:123}});
test('a full personal wallet is not displayed as the nearly exhausted shared allowance',()=>{
 const {window}=parseHTML('<html><body><div id="quota-visual"></div></body></html>');globalThis.document=window.document;
 const value=limits();value.forecast={future_reserved_milliusd:0,accrued_estimate_milliusd:0,legacy_unallocated_milliusd:0};
 renderQuotaVisual(value);const text=document.body.textContent;
 assert.equal(document.querySelector('#quota-visual').hasAttribute('data-wallet'),true);
 assert.match(text,/Your forecast wallet/);assert.match(text,/10\.000/);assert.match(text,/0\.123/);
 assert.match(text,/account lifetime/);assert.doesNotMatch(text,/project lifetime/);
 assert.equal(document.querySelectorAll('[role=progressbar]')[1].getAttribute('aria-valuenow'),'10000');
});
test('platform shortage preserves wallet and gives the exact separate reason',()=>{
 const value=limits(),decision=budgetDecision(value,{approved:true,total_milliusd:497});
 assert.equal(decision.allowed,false);assert.equal(decision.scope,'PLATFORM');
 assert.match(decision.message,/10\.000/);assert.match(decision.message,/0\.123/);assert.match(decision.message,/0\.497/);
 assert.equal(value.wallet.balance_milliusd,10000);
 assert.equal(errorText({code:'BUDGET_EXCEEDED',budget_scope:'PLATFORM',wallet_balance_milliusd:10000,platform_remaining_milliusd:123,required_milliusd:497}),decision.message+' (BUDGET_EXCEEDED)');
});
test('personal shortage, unknown prices and quota are not confused with platform funds',()=>{
 const value=limits();value.wallet.balance_milliusd=10;
 assert.equal(budgetDecision(value,{approved:true,total_milliusd:497}).scope,'ACCOUNT_WALLET');
 assert.equal(budgetDecision(value,{approved:false,total_milliusd:null}).message,t('wallet.prices'));
 value.wallet.balance_milliusd=10000;value.platform_budget.remaining_milliusd=10000;value.remaining_environments=0;
 assert.equal(budgetDecision(value,{approved:true,total_milliusd:497}).scope,'ENVIRONMENT_QUOTA');
 assert.equal(budgetDecision(null,{approved:true,total_milliusd:1}).allowed,false);
});
test('old responses retain conservative admission; wallet grant alone never authorizes AWS spend',()=>{
 assert.equal(budgetDecision({remaining_environments:2,remaining_milliusd:123},{approved:true,total_milliusd:497}).allowed,false);
 const value=limits();value.platform_budget.remaining_milliusd=10000;
 assert.equal(budgetDecision(value,{approved:true,total_milliusd:497}).allowed,true);
});
test('wizard displays specific platform refusal while preserving form and confirmation fencing',async()=>{
 const value=limits();let creates=0;
 const flow=createCreationFlow({estimate:async request=>({...request,approved:true,total_milliusd:497,first_period:{},renewal_period:{},after_shutdown:{},preview:{}}),
  create:async()=>{creates++;},costAllowed:q=>budgetDecision(value,q).allowed,costError:q=>budgetDecision(value,q).message,keyFor:()=> 'local-wallet-key'});
 flow.open({template_id:'T01',create_enabled:true});flow.change({estimateHours:'4'});await flow.next();await flow.next();
 assert.equal(flow.snapshot().step,2);assert.equal(flow.snapshot().form.estimateHours,'4');assert.match(flow.snapshot().error,/shared platform/);
 flow.consent(true);await flow.submit();assert.equal(creates,0);assert.equal(flow.snapshot().consent,false);
});
