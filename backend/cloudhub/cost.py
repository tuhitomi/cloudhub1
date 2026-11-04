"""F03: no invented regional rates; signed-off deployment supplies actual units."""
import json
from decimal import Decimal, ROUND_CEILING
from .errors import HubError
from collections import defaultdict

class _UnknownPrice:
    """Unknown propagates through a line item; never interpreted as a zero rate."""
    def __add__(self,other):return self
    __radd__=__add__
    __mul__=__add__
    __rmul__=__add__
UNKNOWN_PRICE=_UnknownPrice()

REQUIRED_RATES = {"ec2_hour", "ebs_gib_month", "ipv4_hour", "snapshot_gib_month",
                  "transfer_gib", "logs_gib", "control_plane_session"}
S3_RATES = {"s3_gib_month", "s3_requests_1000", "cloudfront_transfer_gib", "cloudfront_requests_10000",
            "logs_gib", "control_plane_session"}
BASE_RATES={'logs_gib','control_plane_session','transfer_gib'}
RATE_REQUIREMENTS={
    'T01':REQUIRED_RATES,'T05':REQUIRED_RATES,'T02':S3_RATES,
    'T07':BASE_RATES|{'s3_gib_month','s3_requests_1000'},
    'T03':BASE_RATES|{'ec2_hour','ebs_gib_month','ipv4_hour','rds_hour','rds_gib_month','rds_snapshot_gib_month','secret_month','secret_requests_10000'},
    'T04':BASE_RATES|{'ec2_hour','ebs_gib_month','ipv4_hour','rds_hour','rds_gib_month','rds_snapshot_gib_month','secret_month','secret_requests_10000','alb_hour','alb_lcu_hour'},
    'T06':BASE_RATES|{'fargate_vcpu_hour','fargate_gib_hour','alb_hour','alb_lcu_hour','ipv4_hour','s3_gib_month','s3_requests_1000','ecr_gib_month'},
    'T08':BASE_RATES|{'ec2_hour','ebs_gib_month','ipv4_hour','efs_gib_month','efs_backup_gib_month','efs_restore_gib'},
    'T09':BASE_RATES|{'api_requests_million','lambda_requests_million','lambda_gib_second','dynamodb_reads_million','dynamodb_writes_million','dynamodb_gib_month','s3_gib_month','s3_requests_1000'},
    'T10':BASE_RATES|{'redshift_rpu_hour','redshift_gib_month','redshift_snapshot_gib_month','s3_gib_month','s3_requests_1000','secret_month','secret_requests_10000'}
}

class Estimator:
    def __init__(self, rates=None):
        self.rates = rates or {}

    def for_region(self,region):
        if region==self.rates.get('region'):return self
        value=self.rates.get('regional_rates',{}).get(region,{})
        if value.get('region')!=region:
            value={'approved':False,'region':region,'units':{},'updated_at':None}
        selected=Estimator(value)
        selected.control_rates=self.rates
        return selected

    def estimate(self, template_id, duration_hours, *, renewal=False, backup=True, configuration=None, workload=None):
        from .catalog import resolve_configuration
        cfg=resolve_configuration(template_id,configuration)
        if workload is not None:
            from .workload_cost import apply
            return apply(self,template_id,duration_hours,cfg,self.estimate(template_id,duration_hours,renewal=renewal,backup=backup,configuration=cfg),workload)
        required = set(RATE_REQUIREMENTS[template_id])
        if template_id=='T02' and (cfg.get('max_file_bytes',0)>8192 or 'cloudfront_functions_million' in self.rates.get('units',{})):required.add('cloudfront_functions_million')
        overrides=self.rates.get('template_rate_overrides',{}).get(template_id,{})
        rate_units={**self.rates.get('units',{}),**overrides.get('units',{})}
        unit_regions={**self.rates.get('unit_regions',{}),**overrides.get('unit_regions',{})}
        approved = self.rates.get("approved", False) and required <= rate_units.keys()
        assumptions = {"duration_hours": duration_hours, "provisioning_hours": "0.25",
                       "root_gib": 16, "data_gib": 8, "backup_gib": 8, "backup_retention_days": 7,
                       "transfer_gib": 1, "logs_gib": "0.1", "month_hours": 730,
                       "backup_outage_hours": "0.25"}
        if template_id == "T02":
            assumptions = {"duration_hours": duration_hours, "provisioning_hours": "0.5", "max_files": 32,
                "max_file_bytes": 8192, "max_total_bytes": 262144, "max_writes": 128,
                "source_with_versions_gib": "0.002", "backup_gib": "0.0003", "backup_retention_days": 7,
                "s3_requests": 2000, "cloudfront_transfer_gib": 1, "cloudfront_requests": 10000,
                "logs_gib": "0.1", "month_hours": 730, "backup_outage_hours": 0}
            assumptions['cloudfront_pricing_scope']=self.rates.get('cloudfront_pricing_scope',
                'Global CloudFront, US-DataTransfer-Out-Bytes and US-Requests-Tier2-HTTPS. Viewer geography can change actual rates independently of the origin Region.')
        if template_id not in {'T01','T02','T05'}:
            assumptions={'duration_hours':duration_hours,'provisioning_and_backup_hours':'1.5','month_hours':730,
                'backup_retention_days':7,'transfer_gib':1,'logs_gib':'0.1','max_operations':128,'configuration':cfg,
                'cost_bound':'Usage envelope estimate, not a hard AWS billing cap.'+
                    (' ALB assumes one LCU.' if template_id in {'T04','T06'} else '')+
                    (' Redshift assumes continuous 8 RPU compute.' if template_id=='T10' else '')}
        assumptions['configuration']=cfg
        # Workload location and shared management components need separate price scopes.
        # For example T07 has no workload CloudWatch log group: its workflow logs stay home.
        price_regions={key:unit_regions.get(key,
            'global' if key.startswith('cloudfront_') else self.rates.get('control_region',self.rates.get('region')) if key=='control_plane_session' else self.rates.get('region'))
            for key in sorted(required)}
        assumptions['price_regions']=price_regions
        if template_id in {'T01','T05'}:assumptions.update(root_gib=cfg['root_gib'],data_gib=cfg['data_gib'],backup_gib=cfg['data_gib'])
        file_scale=Decimal(cfg.get('max_total_bytes',262144))/262144
        source_gib=max(Decimal('.002')*file_scale,Decimal(cfg.get('max_writes',0))*cfg.get('max_file_bytes',0)/(1024**3))
        backup_gib=max(Decimal('.0003')*file_scale,Decimal(cfg.get('max_total_bytes',0))/(1024**3))
        if template_id in {'T02','T07'}:assumptions.update(upload_and_version_envelope_gib=str(source_gib),signed_upload_lifetime_seconds=120,staging_retention_days=1)
        if template_id=='T02':assumptions.update({k:cfg[k] for k in ('max_files','max_file_bytes','max_total_bytes','max_writes')},source_with_versions_gib=str(source_gib),backup_gib=str(backup_gib))
        u = defaultdict(lambda:UNKNOWN_PRICE,{k: Decimal(str(v)) for k, v in rate_units.items()})
        overhead = Decimal(0) if renewal else Decimal('0.5')
        retention = Decimal(0) if renewal or not backup else Decimal(7*24)/730
        hours = Decimal(duration_hours) + overhead
        if template_id == "T02":
            lines = {"storage": hours * source_gib / 730 * u["s3_gib_month"],
                "backup": backup_gib * retention * u["s3_gib_month"],
                "s3_requests": Decimal(max(2000,cfg.get("max_writes",128)*8+cfg.get("max_files",32)*10))/1000 * u["s3_requests_1000"], "transfer": u["cloudfront_transfer_gib"],
                "cloudfront_requests": u["cloudfront_requests_10000"], "logs": Decimal("0.1") * u["logs_gib"],
                "control_plane": u["control_plane_session"]}
        elif template_id in {'T01','T05'}:
            lines = {"compute": hours * u["ec2_hour"], "storage": hours * (cfg['root_gib']+cfg['data_gib']) / 730 * u["ebs_gib_month"],
                     "ipv4": hours * u["ipv4_hour"], "backup": Decimal(cfg['data_gib']) * retention * u["snapshot_gib_month"],
                     "transfer": u["transfer_gib"], "logs": Decimal("0.1") * u["logs_gib"],
                     "control_plane": u["control_plane_session"]}
        else:
            hours=Decimal(duration_hours)+(Decimal(0) if renewal else Decimal('1.5'))
            lines={'transfer':u['transfer_gib'],'logs':Decimal('.1')*u['logs_gib'],'control_plane':u['control_plane_session']}
            if template_id in {'T03','T04','T08'}:
                nodes=2 if template_id in {'T04','T08'} else 1
                lines.update(compute=hours*nodes*u['ec2_hour'],root_storage=hours*nodes*cfg['root_gib']/730*u['ebs_gib_month'],ipv4=hours*nodes*u['ipv4_hour'])
            if template_id in {'T03','T04'}:
                lines.update(database=hours*u['rds_hour'],db_storage=hours*cfg['db_gib']/730*u['rds_gib_month'],backup=cfg['db_gib']*retention*u['rds_snapshot_gib_month'],
                    secrets=hours/730*u['secret_month']+Decimal('.1')*u['secret_requests_10000'])
            if template_id in {'T04','T06'}:lines.update(load_balancer=hours*(u['alb_hour']+u['alb_lcu_hour']),alb_ipv4=hours*2*u['ipv4_hour'])
            if template_id in {'T06','T07','T09','T10'}:
                lines.update(s3_storage=hours*source_gib/730*u['s3_gib_month'],s3_backup=backup_gib*retention*u['s3_gib_month'],s3_requests=Decimal(max(2000,cfg.get('max_writes',128)*8+cfg.get('max_files',32)*10))/1000*u['s3_requests_1000'])
            if template_id=='T06':lines.update(container=hours*(Decimal(cfg['cpu'])/1024*u['fargate_vcpu_hour']+Decimal(cfg['memory_mib'])/1024*u['fargate_gib_hour']),
                task_ipv4=hours*u['ipv4_hour'],image_storage=Decimal('.5')*(Decimal(duration_hours) if renewal else 24*7)/730*u['ecr_gib_month'])
            if template_id=='T08':lines.update(efs=hours*Decimal('.01')/730*u['efs_gib_month'],backup=Decimal('.02')*retention*u['efs_backup_gib_month'],restore_allowance=Decimal(0) if renewal else Decimal('.02')*u['efs_restore_gib'])
            if template_id=='T09':lines.update(api=Decimal('.01')*u['api_requests_million'],lambda_requests=Decimal('.01')*u['lambda_requests_million'],
                lambda_compute=Decimal(10000)*Decimal(cfg['lambda_memory_mib'])/1024*Decimal('.5')*u['lambda_gib_second'],
                database=Decimal('.02')*(u['dynamodb_reads_million']+u['dynamodb_writes_million'])+hours*Decimal('.01')/730*u['dynamodb_gib_month'])
            if template_id=='T10':lines.update(warehouse=hours*8*u['redshift_rpu_hour'],warehouse_storage=hours/730*u['redshift_gib_month'],
                warehouse_backup=retention*u['redshift_snapshot_gib_month'],secrets=hours/730*u['secret_month']+Decimal('.1')*u['secret_requests_10000'])
        if template_id in {'T02','T07'}:lines['isolated_staging_storage']=source_gib*24/730*u['s3_gib_month']
        if template_id=='T02' and 'cloudfront_functions_million' in u:lines['viewer_function']=Decimal('.01')*u['cloudfront_functions_million']
        known = sum((v for v in lines.values() if v is not UNKNOWN_PRICE),Decimal(0))*Decimal('1.2')
        total = known if approved else None
        assumptions.update(estimate_kind='renewal' if renewal else 'first_period',
            provisioning_allowance_included=not renewal,backup_allowance_included=bool(retention),
            usage_envelope='Lưu lượng, request, log và điều khiển là dự phòng riêng cho từng kỳ, không phải số đo thực tế.')
        if renewal:
            assumptions.update(provisioning_hours=0,provisioning_and_backup_hours=0,backup_outage_hours=0,backup_retention_days=0)
        elif not backup:assumptions['backup_retention_days']=0
        return {"template_id": template_id, "currency": "USD", "approved": bool(approved),
                "region": self.rates.get("region"), "price_updated_at": self.rates.get("updated_at"),
                "units": {key:rate_units.get(key) for key in sorted(required)}, "unit_regions":price_regions,
                "lines": {k: None if v is UNKNOWN_PRICE else str(v) for k, v in lines.items()},"total_usd":str(total) if total is not None else None,
                "known_subtotal_usd":str(known),"known_subtotal_milliusd":int((known*1000).to_integral_value(rounding=ROUND_CEILING)),
                "missing_components":['price:'+key for key in sorted(required-rate_units.keys())]+([] if self.rates.get('approved') else ['price:approval']),
                "cost_complete":bool(approved),
                "assumptions": assumptions, "contingency_percent": 20,
                "total_milliusd": int((total * 1000).to_integral_value(rounding=ROUND_CEILING)) if total is not None else None,
                "unknown": ["Chi phí thực tế phụ thuộc lưu lượng, log và thời gian xử lý; quota không phải giới hạn hóa đơn AWS."],
                "cost_data_delay": "Billing/Cost Explorer có độ trễ; không dùng để khóa quota đồng thời."}

    def holding(self, template_id, ending_policy, configuration=None, workload=None):
        """Known storage only; shared infrastructure and unmeasured usage remain explicit."""
        from .catalog import resolve_configuration
        cfg=resolve_configuration(template_id,configuration)
        if workload is not None:
            from .workload_cost import apply
            base=self.holding(template_id,ending_policy,configuration)
            return apply(self,template_id,base['period_hours'],cfg,base,workload,holding=True)
        if ending_policy=='PAUSE':
            rates={'ebs_gib_month':Decimal(cfg['root_gib']+cfg['data_gib'])};hours=24
        elif template_id in {'T01','T05'}:rates={'snapshot_gib_month':Decimal(cfg['data_gib'])};hours=7*24
        elif template_id in {'T03','T04'}:rates={'rds_snapshot_gib_month':Decimal(cfg['db_gib'])};hours=7*24
        elif template_id=='T08':rates={'efs_backup_gib_month':Decimal('.02')};hours=7*24
        elif template_id=='T10':rates={'redshift_snapshot_gib_month':Decimal(1),'s3_gib_month':Decimal('.0003')};hours=7*24
        else:rates={'s3_gib_month':Decimal('.0003')*Decimal(cfg.get('max_total_bytes',262144))/262144};hours=7*24
        units=self.rates.get('units',{});approved=bool(self.rates.get('approved')) and set(rates)<=units.keys()
        total=sum(size*Decimal(hours)/730*Decimal(str(units[key])) for key,size in rates.items())*Decimal('1.2') if approved else None
        return {'approved':approved,'currency':'USD','ending_policy':ending_policy,'period_hours':hours,
            'total_milliusd':int((total*1000).to_integral_value(rounding=ROUND_CEILING)) if total is not None else None,
            'units':{key:units.get(key) for key in rates},'storage_gib':{key:str(size) for key,size in rates.items()},
            'price_updated_at':self.rates.get('updated_at'),'region':self.rates.get('region'),'contingency_percent':20,
            'continues_until_manual_retirement':ending_policy=='PAUSE',
            'unknown':['Giữ dữ liệu khi tạm dừng tiếp tục phát sinh phí sau 24 giờ cho đến khi thu hồi.','Chưa tính log lưu lâu, bản sao cũ, hạ tầng dùng chung và lưu lượng chưa đo.'] if ending_policy=='PAUSE' else ['Bản sao cũ, log và hạ tầng dùng chung có thể tiếp tục phát sinh phí; dữ liệu thực tế có thể lớn hơn giả định.']}
