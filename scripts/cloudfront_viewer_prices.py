"""Fetch public On-Demand rates; no AWS credentials/mutations; explicit review required."""
import csv,io,json,urllib.request,argparse,hashlib
from decimal import Decimal
from datetime import datetime,timezone
URL='https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonCloudFront/current/index.csv'
GROUPS={'US':['US','CA'],'EU':['EU'],'APAC':['AP','JP','AU','IN'],'OTHER':['ME','ZA','SA']}

def build(rows,version,updated):
    rates={}
    for row in rows:
        usage=row.get('usageType','');code=usage.split('-',1)[0]
        if row.get('TermType')!='OnDemand' or row.get('Currency')!='USD' or row.get('StartingRange')!='0' or code not in {c for group in GROUPS.values() for c in group}:continue
        key='cloudfront_transfer_gib' if usage.endswith('-DataTransfer-Out-Bytes') and row.get('EndingRange')=='10240' else 'cloudfront_requests_10000' if usage.endswith('-Requests-Tier2-HTTPS') else None
        if not key:continue
        rate=Decimal(row['PricePerUnit'])*(10000 if key.endswith('10000') else 1)
        rates.setdefault(code,{})[key]={'value':str(rate),'sku':row['SKU'],'rate_code':row['RateCode'],'aws_unit':row['Unit'],'source_url':URL}
    if any(set(rates.get(c,{}))!={'cloudfront_transfer_gib','cloudfront_requests_10000'} for group in GROUPS.values() for c in group):raise ValueError('Missing/changed regional price dimension; review AWS offer.')
    # T02 IaC uses PriceClass_100, not All. Viewer geography is never rewritten.
    # Estimate conservatively over every eligible billing group, rather than
    # claim the viewer country determines the POP that CloudFront selects.
    eligible=['US','CA','EU'];units={key:str(max(Decimal(rates[c][key]['value']) for c in eligible)) for key in rates['US']}
    viewers={key:{'approved':False,'updated_at':updated,'units':units.copy(),'price_class':'PriceClass_100',
        'viewer_billing_groups':group,'charged_groups':eligible,'selection':'MAX_ELIGIBLE_EDGE_RATE','price_version':version,
        'source_url':URL} for key,group in GROUPS.items()}
    return {'schema':1,'approved':False,'updated_at':updated,'price_version':version,'source_url':URL,'edge_rates':rates,'viewers':viewers}

def fetch():
    with urllib.request.urlopen(URL,timeout=60) as res:
        stream=io.TextIOWrapper(res,encoding='utf-8-sig');meta=[next(csv.reader([stream.readline()])) for _ in range(5)]
        return build(csv.DictReader(stream),dict(meta)['Version'],datetime.now(timezone.utc).isoformat())

if __name__=='__main__':
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out',required=True);args=parser.parse_args()
    Path(args.out).write_text(json.dumps(fetch(),indent=2)+'\n',encoding='utf-8');print('Fetched official prices; approved remains false pending review.')
