"""Operator-controlled commercial Regions and persisted resource provenance."""
import re
from copy import deepcopy
from .errors import HubError
from .catalog import ACTIVE_TEMPLATES, configuration_profiles, configuration_verified, configuration_key
from .cost import RATE_REQUIREMENTS

REGIONS = {'ap-southeast-1':'Singapore','ap-northeast-1':'Tokyo','us-east-1':'Northern Virginia, United States'}
REGIONAL_KEYS = {'ami_id','availability_zone','vpc_id','public_subnet_id','public_subnet_ids',
    'db_subnet_ids','postgres_version','approved_image','s3_backup_bucket','backup_vault',
    'backup_role','backup_restore_role','cf_role_arn','permissions_boundary','instance_profile',
    'ssh_cidr','kms_key_arn','management_table','management_table_arn','cognito_client_id',
    'cognito_issuer','frontend_origin','schedule_group','scheduler_role','expiry_arn','dlq_arn','region'}

def record_region(row, settings):
    """Never derive a deletion target from caller query parameters or an arbitrary ID."""
    explicit=row.get('region')
    observed=set()
    for value in [row.get(k) for k in ('source','backup_arn','recovery_arn','snapshot_arn','aws_recovery_point_arn','recovery_point_arn','db_snapshot_arn','redshift_snapshot_arn','stack_id')]+[
                  row.get('estimate',{}).get('region')]:
        if not isinstance(value,str):continue
        match=re.match(r'^arn:aws:[^:]+:([a-z]{2}-[a-z]+-\d):',value)
        if match:observed.add(match.group(1))
        elif value in REGIONS:observed.add(value)
    for resource in row.get('resources',[]):
        # Explicit inventory location is authoritative. IAM/CloudFront are global.
        if resource.get('region') in REGIONS:observed.add(resource['region'])
    if explicit:
        if explicit not in REGIONS or observed-{explicit}:
            raise HubError('RESOURCE_REGION_MISMATCH','Stored resource Region does not match its provenance.',409)
        return explicit
    if len(observed)==1:return next(iter(observed))
    binding=settings.get('legacy_region_binding',{})
    if not observed and binding.get('verified') is True and binding.get('region') in REGIONS:
        return binding['region']
    raise HubError('REGION_PROVENANCE_REQUIRED','Verify the original Region before operating on legacy resources.',409)

def regional_settings(settings,row):
    selected=record_region(row,settings);home=settings.get('control_region',settings.get('region'))
    if selected==home:
        result=deepcopy(settings)
    else:
        profile=settings.get('regions',{}).get(selected)
        if not isinstance(profile,dict) or profile.get('prepared') is not True:
            raise HubError('REGION_NOT_PREPARED','Regional infrastructure settings are not prepared.',409)
        # Do not inherit home AMIs, networks, secrets, backups or KMS identifiers.
        result={k:deepcopy(v) for k,v in settings.items() if k not in REGIONAL_KEYS and k!='regions'}
        result.update(deepcopy(profile))
        result.update({k:settings[k] for k in ('management_table','management_table_arn','cognito_client_id',
            'cognito_issuer','frontend_origin','schedule_group','scheduler_role','expiry_arn','dlq_arn') if k in settings})
        required={'account_id','region','cf_role_arn','s3_backup_bucket'}
        if not required<=result.keys() or result['region']!=selected:
            raise HubError('REGION_NOT_PREPARED','Regional settings are incomplete or mismatched.',409)
        for key in ('kms_key_arn',):
            if result.get(key) and f':{selected}:' not in result[key]:
                raise HubError('RESOURCE_REGION_MISMATCH','Regional KMS key does not match the selected Region.',409)
    result.update(region=selected,control_region=home)
    if result.get('availability_zone') and not re.fullmatch(re.escape(selected)+'[a-z]',result['availability_zone']):
        raise HubError('REGION_NOT_PREPARED','Local Zones, Wavelength and mismatched availability zones are not supported.',409)
    if row.get('backup_bucket') and row['backup_bucket']!=result.get('s3_backup_bucket'):
        raise HubError('RESOURCE_REGION_MISMATCH','Backup storage changed; verify its original location before operating.',409)
    return result

def client_region(service,settings):
    if service in {'iam','cloudfront'}:return 'us-east-1'
    if service=='scheduler':return settings.get('control_region',settings['region'])
    return settings['region']

class RegionRegistry:
    def __init__(self,home,rates,config=None):
        if home not in REGIONS:raise HubError('REGION_NOT_ALLOWED','Control Region is not configured in the allowlist.',409)
        self.home,self.rates,self.config=home,rates,config or {}
    def select(self,value=None):
        if value is None:return self.home
        if not isinstance(value,str) or value not in REGIONS:
            raise HubError('REGION_NOT_ALLOWED','Choose a CloudHub-approved AWS Region.',409)
        return value
    def options(self,tid,verified):
        result=[]
        for region,name in REGIONS.items():
            policy=self.config.get('regions',{}).get(region,{})
            rates=self.rates if region==self.home else self.rates.get('regional_rates',{}).get(region,{})
            profiles=[]
            for profile in configuration_profiles(tid):
                if region==self.home:
                    # Home-region additive proofs can use the existing regional
                    # shard instead of overflowing the retained price document.
                    proofs={**rates.get('configuration_verifications',{}),**policy.get('verifications',{})}
                    passed=configuration_verified(tid,profile['configuration'],verified,proofs)
                    enabled=policy.get('enabled',True)
                else:
                    proof=policy.get('verifications',{}).get(configuration_key(tid,profile['configuration']),{})
                    passed=proof.get('passed') is True and proof.get('region')==region and proof.get('provisioning_checks',0)>=2 and proof.get('backup_restore_verified') is True
                    enabled=policy.get('enabled') is True and policy.get('prepared') is True
                operationally_enabled=enabled
                enabled=enabled and rates.get('approved') is True and rates.get('region')==region and RATE_REQUIREMENTS[tid]<=rates.get('units',{}).keys()
                state='SUPPORTED' if passed and enabled else 'VERIFYING' if policy.get('prepared') or region==self.home else 'UNAVAILABLE'
                profiles.append({**profile,'create_enabled':bool(passed and enabled),'verification_passed':bool(passed),'enabled':bool(operationally_enabled),'status':state})
            result.append({'region':region,'name':name,'status':'SUPPORTED' if any(p['create_enabled'] for p in profiles) else 'VERIFYING' if policy.get('prepared') else 'UNAVAILABLE',
                'configuration_options':profiles,'prices_available':rates.get('approved') is True and rates.get('region')==region and RATE_REQUIREMENTS[tid]<=rates.get('units',{}).keys()})
        return result
    def verified(self,tid,cfg,region,verified):
        return any(r['region']==region and any(p['configuration']==cfg and p['verification_passed'] and p['enabled'] for p in r['configuration_options']) for r in self.options(tid,verified))
