import {t,number} from './i18n.js';
export const templateText=(row,kind='name')=>/^T0[1-9]$/.test(row?.template_id||'')?t('template.'+row.template_id+'.'+kind):(row?.[kind]||'CloudHub');
export const backupScope=row=>/^T0[1-9]$/.test(row?.template_id||'')?t('scope.'+row.template_id):(row?.scope||row?.backup_scope||t('common.unknown'));
export const regionLabel=row=>['ap-southeast-1','ap-northeast-1','us-east-1'].includes(row?.region)?t('region.'+row.region):(row?.name||row?.region||t('common.unknown'));
export function profileLabel(row,profile){
 const c=profile?.configuration;if(!c)return profile?.label||t('config.hardware');
 if(c.data_gib!=null)return t('config.dataDisk')+' '+number(c.data_gib)+' GiB';
 if(c.db_gib!=null)return 'PostgreSQL '+number(c.db_gib)+' GiB';
 if(c.cpu!=null)return 'Docker '+number(c.cpu/1024)+' vCPU · '+number(c.memory_mib/1024)+' GiB RAM';
 if(c.nodes!=null)return number(c.nodes)+' EC2 · '+t('config.root')+' '+number(c.root_gib)+' GiB';
 if(c.lambda_memory_mib!=null)return 'API · Lambda '+number(c.lambda_memory_mib)+' MiB';
 if(c.max_files!=null)return t('config.files')+' '+number(c.max_files)+' · '+number(c.max_total_bytes/1024)+' KiB';
 return t('config.hardware');
}
export const profileDescription=(row,profile)=>templateText(row,'purpose')+' · '+profileLabel(row,profile);
