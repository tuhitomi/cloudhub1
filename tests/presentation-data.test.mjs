import {setLanguage} from '../frontend/i18n.js';
await setLanguage('vi',{persist:false});
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {environmentOverview,operationPresentation,accessInstructions} from '../frontend/presentation-data.js';
test('no actual bill inferred from empty or missing cost reports',()=>{const overview=environmentOverview([{status:'READY',estimated_committed_milliusd:1200},{status:'DELETED',estimate:{total_milliusd:300},cost_report:{actual_milliusd:null}}]);assert.equal(overview.estimateText,'1,500\u00a0USD');assert.equal(overview.actualCostText,'Chưa có dữ liệu đối soát');assert.match(overview.coverageText,/ghi nhận 0\/2/);});
test('zero actual report is a measured zero; partial coverage stated separately from forecast',()=>{const overview=environmentOverview([{status:'PAUSED',cost_report:{actual_milliusd:0},estimated_committed_milliusd:1000},{status:'ERROR_RETAINED'}]);assert.equal(overview.actualCostText,'0,000\u00a0USD');assert.match(overview.coverageText,/ghi nhận 1\/2/);assert.equal(overview.stats[2].value,'1 môi trường');assert.equal(overview.stats[3].value,'1 môi trường');});
test('long running operation has meaningful phase and next step without invented progress percent',()=>{const view=operationPresentation({action:'backup',status:'RUNNING',phase:'WAIT_BACKUP'});assert.match(view.phase,/Chờ bản sao/);assert.doesNotMatch(JSON.stringify(view),/%/);assert.match(view.nextStep,/không cần gửi lại/);assert.match(accessInstructions('T10'),/chưa được mở/);});

test('file and recovery phases do not expose internal enum labels',()=>{for(const phase of ['WRITE_FILE','DELETE_BACKUP','EXPORT_BACKUP','COST','DEPLOY_APPLICATION'])assert.doesNotMatch(operationPresentation({action:'backup',status:'RUNNING',phase}).phase,new RegExp(phase));});
