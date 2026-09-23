import {t,money} from './i18n.js';
const aliases={"UNAUTHORIZED": "ui.767cdc9a7082", "ACCOUNT_DISABLED": "ui.871f88cb44d4", "EMAIL_NOT_VERIFIED": "ui.36b45c9ead3c", "TEMPLATE_UNAVAILABLE": "ui.a1da59da2e8e", "TEMPLATE_UNVERIFIED": "ui.581383befb9a", "CONFIGURATION_UNVERIFIED": "ui.581383befb9a", "CUMULATIVE_BUDGET_EXCEEDED": "ui.be44b2c62beb", "RECOVERY_REGION_MISMATCH": "error.CROSS_REGION_RESTORE"};
export function errorText(error){
 if(error?.code==='BUDGET_EXCEEDED'&&error.budget_scope==='ACCOUNT_WALLET')return t('wallet.insufficient',{balance:money(error.wallet_balance_milliusd),required:money(error.required_milliusd)})+' (BUDGET_EXCEEDED)';
 if(error?.code==='BUDGET_EXCEEDED'&&error.budget_scope==='PLATFORM')return t('wallet.platformShort',{balance:money(error.wallet_balance_milliusd),available:money(error.platform_remaining_milliusd),required:money(error.required_milliusd)})+' (BUDGET_EXCEEDED)';
 if(error?.code?.startsWith('ANNOUNCEMENT_'))return t('maintenance.error')+' ('+error.code+')';
 if(error?.code==='UPLOAD_NOT_VISIBLE')return t('upload.notVisible')+' (UPLOAD_NOT_VISIBLE)';
 if(error?.code==='UPLOAD_INCOMPLETE')return t('upload.incomplete')+' (UPLOAD_INCOMPLETE)';
 const code=error?.code;if(['WORKLOAD_INVALID','WORKLOAD_CONFLICT','WORKLOAD_CONFIGURATION_MISMATCH'].includes(code))return t('error.'+code)+' ('+code+')';if(code?.startsWith('APPLICATION_'))return t('ux.app.pending')+' ('+code+')';if(code==='QUOTE_REQUIRED')return t('contract.reload')+' ('+code+')';if(code?.startsWith('QUOTE_'))return t('quote.review')+' ('+code+')';if(code==='RELEASE_UNVERSIONED_REFERENCE')return (error.file?t('release.invalidReference',{file:error.file,path:error.asset_path||'/'}):t('release.relative'))+' ('+code+')';if(!code)return error?.message||String(error);
 if(code.startsWith('REGION_')||code==='RESOURCE_REGION_MISMATCH'||code==='CROSS_REGION_RESTORE')return t('error.'+code)+' ('+code+')';
 // The diagnostic code remains intact; localized guidance is shown separately.
 return t(aliases[code]||'error.generic')+' ('+code+')';
}
