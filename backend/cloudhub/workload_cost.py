"""Price declared usage with the same approved regional rates and safety floor.

No rates, free-tier deductions or performance multipliers are invented here.
Existing envelope lines are floors; unknown prices/quantities never become zero.
"""
from decimal import Decimal,ROUND_CEILING
from copy import deepcopy
from .workloads import normalize,demand,BASIC_DEFAULTS

def apply(estimator,tid,hours,cfg,result,workload,*,holding=False):
    w=normalize(tid,workload);result=deepcopy(result);d=demand(tid,w,hours)
    result.setdefault('assumptions',{}).update(planning_workload=w,workload_schema='workload-1',demand=d,
        workload_is_capacity=False,usage_pricing_policy='MAX_OF_EXISTING_ENVELOPE_AND_DECLARED_DEMAND',
        basic_model_defaults=BASIC_DEFAULTS.get(tid,{}),optional_cpu_memory_are_not_capacity=True)
    if not result['approved']:return result
    units={**estimator.rates.get('units',{}),**estimator.rates.get('template_rate_overrides',{}).get(tid,{}).get('units',{})}
    lines={k:Decimal(str(v)) for k,v in result.get('lines',{}).items()};missing=[]
    def amount(key):return None if d.get(key) is None else Decimal(d[key])
    def floor(line,quantity,rate,divisor=1):
        if quantity is None:missing.append('usage:'+line);return
        if rate not in units:missing.append('price:'+rate);return
        lines[line]=max(lines.get(line,Decimal(0)),Decimal(quantity)/Decimal(divisor)*Decimal(str(units[rate])))
    if holding:
        if tid=='T08' and w.get('data_mib') is not None:
            original=Decimal(str(result['total_milliusd']))/1000
            value=Decimal(w['data_mib'])/1024*Decimal(hours)/730*Decimal(str(units['efs_backup_gib_month']))*Decimal('1.2')
            result['total_milliusd']=int((max(original,value)*1000).to_integral_value(rounding=ROUND_CEILING))
        return result
    if tid=='T02':
        scope=w.get('viewer_geography')
        # Existing reviewed CloudFront prices are scoped to US viewers. Origin
        # Region alone cannot validate prices for viewers in a different area.
        viewer=estimator.rates.get('cloudfront_viewer_rates',{}).get(scope,{})
        if viewer.get('approved') is True and viewer.get('updated_at') and viewer.get('price_class','PriceClass_100')=='PriceClass_100' and {'cloudfront_transfer_gib','cloudfront_requests_10000'}<=viewer.get('units',{}).keys():
            units.update(viewer['units']);result['assumptions'].update(viewer_price_updated_at=viewer['updated_at'],
                cloudfront_price_class='PriceClass_100',viewer_price_version=viewer.get('price_version'),
                viewer_charged_groups=viewer.get('charged_groups',[]),viewer_price_selection=viewer.get('selection'),viewer_price_source=viewer.get('source_url'))
            lines['transfer']=Decimal(str(result['assumptions'].get('cloudfront_transfer_gib',1)))*Decimal(str(units['cloudfront_transfer_gib']))
            lines['cloudfront_requests']=Decimal(str(result['assumptions'].get('cloudfront_requests',10000)))/10000*Decimal(str(units['cloudfront_requests_10000']))
            result['units'].update(viewer['units'])
        elif scope!='US':
            missing.append('price:cloudfront_viewer_'+str(scope))
            lines.pop('transfer',None);lines.pop('cloudfront_requests',None)
        result['assumptions']['viewer_geography']=scope
        if not any(x.startswith('price:cloudfront_viewer_') for x in missing):
            floor('transfer',amount('transfer_gib'),'cloudfront_transfer_gib')
            floor('cloudfront_requests',amount('asset_requests'),'cloudfront_requests_10000',10000)
        origin=amount('origin_requests');floor('s3_requests',origin,'s3_requests_1000',1000)
        if 'viewer_function' in lines:floor('viewer_function',amount('asset_requests'),'cloudfront_functions_million',1000000)
    else:
        transfer=amount('transfer_gib')
        if tid=='T04':
            peak=amount('peak_rps');size=w.get('response_kib')
            if peak is None or size is None:transfer=None
            else:transfer=max(transfer or Decimal(0),peak*Decimal(str(hours))*3600*size/1048576)
            result['assumptions']['scaling_cost_scope']='Existing envelope prices two EC2 nodes and one shared RDS. Normal min=1, max=2; peak demand is used for traffic. No scale-out latency assumed.'
        floor('transfer',transfer,'transfer_gib')
    if tid=='T07':
        up=amount('upload_requests');down=amount('download_requests')
        floor('s3_requests',None if up is None or down is None else up+down,'s3_requests_1000',1000)
    if tid in {'T02','T07','T06'}:
        stored=None if w.get('data_kib') is None else Decimal(w['data_kib'])/1048576
        floor('storage' if tid=='T02' else 's3_storage',None if stored is None else stored*Decimal(str(hours))/730,'s3_gib_month')
    if tid=='T08':
        stored=None if w.get('data_mib') is None else Decimal(w['data_mib'])/1024
        floor('efs',None if stored is None else stored*Decimal(str(hours))/730,'efs_gib_month')
        retained=Decimal(str(result['assumptions'].get('backup_retention_days',0)))*24/730
        floor('backup',None if stored is None else stored*retained,'efs_backup_gib_month')
        if 'restore_allowance' in lines and lines['restore_allowance']>0:floor('restore_allowance',stored,'efs_restore_gib')
        result['assumptions']['efs_scope']='Current EFS Standard storage in bursting mode. Throughput-mode/IOPS changes are not offered; network charges remain subject to actual traffic and placement.'
        result['assumptions']['efs_throughput_mode']='bursting; Standard storage, no Elastic/Provisioned throughput selected'
    if tid in {'T03','T04'}:
        requests=amount('requests')
        if tid=='T04' and amount('peak_rps') is not None:requests=max(requests or Decimal(0),amount('peak_rps')*Decimal(str(hours))*3600)
        if requests is None:missing.append('usage:application_secret_reads')
        elif 'secret_requests_10000' not in units:missing.append('price:secret_requests_10000')
        else:
            usage=requests/10000*Decimal(str(units['secret_requests_10000']))
            lines['application_secret_reads']=max(Decimal(0),usage-Decimal('.1')*Decimal(str(units['secret_requests_10000'])))
            result['assumptions']['application_database_path']='Current sample GET opens PostgreSQL and reads Secrets Manager per request. Arbitrary queries/custom application deployment not included.'
    if tid in {'T04','T06'}:
        transferred=amount('transfer_gib')
        if tid=='T04' and amount('peak_rps') is not None and w.get('response_kib') is not None:transferred=max(transferred or Decimal(0),amount('peak_rps')*Decimal(str(hours))*3600*w['response_kib']/1048576)
        if transferred is None:missing.append('usage:alb_processed_bytes')
        else:
            # One LCU permits 1 decimal GB/h for EC2/container targets. Request
            # bytes are not collected for these templates; identify that gap.
            lcu=max(Decimal(1),transferred*Decimal(1024**3)/Decimal(10**9)/Decimal(str(hours)))
            lines['load_balancer']=max(lines['load_balancer'],Decimal(str(hours))*(Decimal(str(units['alb_hour']))+lcu*Decimal(str(units['alb_lcu_hour']))))
        result['assumptions']['alb_cost_scope']='MAX(existing one-LCU envelope, declared response bytes at 1 GB per LCU-hour). Request bytes, connection lifetime/rate and rule evaluations are not specified; actual max-dimension LCU charges may be higher.'
    if tid=='T09':
        requests=amount('requests');floor('api',requests,'api_requests_million',1000000);floor('lambda_requests',requests,'lambda_requests_million',1000000)
        compute=None if requests is None or w.get('processing_ms') is None else requests*Decimal(w['processing_ms'])/1000*cfg['lambda_memory_mib']/1024
        floor('lambda_compute',compute,'lambda_gib_second')
        if requests is None or any(w.get(k) is None for k in ['reads_per_request','writes_per_request','record_bytes','record_count']):missing.append('usage:dynamodb')
        else:
            # Strongly consistent reads of <=4KiB and writes per 1KiB; expressed
            # as a planning assumption, not an observation of the application.
            size=w['record_bytes'];read_units=max(1,(size+4095)//4096)*max(1,w['record_count']);write_units=(size+1023)//1024
            db=requests/1000000*(max(1,w['reads_per_request'])*read_units*Decimal(str(units['dynamodb_reads_million']))+w['writes_per_request']*write_units*Decimal(str(units['dynamodb_writes_million'])))
            db+=Decimal(w['record_count']*size)/(1024**3)*Decimal(str(hours))/730*Decimal(str(units['dynamodb_gib_month']))
            lines['database']=max(lines['database'],db)
            result['assumptions']['dynamodb_consistency']='Current read API scans all managed records, conservatively rounded per item (4KiB read/1KiB write). PAY_PER_REQUEST. Public API is read-only; mutations are separate CloudHub operations.'
            control=getattr(estimator,'control_rates',estimator.rates)
            rate=control.get('units',{}).get('dynamodb_reads_million')
            if control.get('approved') is not True or rate is None:missing.append('price:management_dynamodb_reads')
            else:
                lines['management_reads']=requests*2/1000000*Decimal(str(rate))
                result['assumptions']['management_read_price']={'unit':str(rate),'region':control.get('region'),'updated_at':control.get('updated_at'),'strong_reads_per_request':2}
    known=sum(lines.values())*Decimal('1.2')
    result.update(lines={k:str(v) for k,v in lines.items()},known_subtotal_usd=str(known),total_usd=str(known) if not missing else None,
        known_subtotal_milliusd=int((known*1000).to_integral_value(rounding=ROUND_CEILING)),
        rounding_policy='Exact decimal USD lines/total; ledger reserves upward to 0.001 USD. Display rounding is independent.',
        missing_components=sorted(set(missing)),cost_complete=not missing)
    result['approved']=not missing
    result['total_milliusd']=result['known_subtotal_milliusd'] if not missing else None
    result['unknown']+=['Workload cost uses declared demand and the existing conservative envelope, not observed traffic or an AWS bill.']
    if tid in {'T04','T06'}:result['unknown'].append(result['assumptions']['alb_cost_scope'])
    if missing:result['unknown'].append('Incomplete price/usage coverage: '+', '.join(sorted(set(missing))))
    return result
