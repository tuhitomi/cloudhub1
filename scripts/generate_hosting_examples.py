"""Generate illustrative CloudFormation only. Does not call AWS or select a domain."""
import json
from pathlib import Path
from generate_infra import build_template
from hosting import config,split_edge,configure_edge,certificate_template,api_template,dns_template,hosted_zone_template

ROOT=Path(__file__).resolve().parents[1]

def generate():
    c=json.loads((ROOT/'config/hosting.example.json').read_text(encoding='utf-8'))
    c.update(ACCOUNT_ID='123456789012',ROOT_DOMAIN='example.com',FRONTEND_DOMAIN='app.example.com',API_DOMAIN='api.example.com',DNS_PROVIDER='route53',ROUTE53_HOSTED_ZONE_ID='ZEXAMPLE')
    c=config(c)
    inventory={'frontend':{'distribution_id':'EEXAMPLE','distribution_domain':'example.cloudfront.net',
        'origins':[{'id':'private-s3','domain':'example-private.s3.ap-southeast-1.amazonaws.com','oac_id':'EOAC'},
                   {'id':'ui-context-api','domain':'api123.execute-api.ap-southeast-1.amazonaws.com'}]},
        'edge_resource_ids':{'UiCountryOriginPolicy':'00000000-0000-0000-0000-000000000000'}}
    shared=split_edge(build_template(),'cloudhub-source',inventory)['import']
    files={'public-zone.example.json':hosted_zone_template(c['ROOT_DOMAIN']),
        'edge-import.example.json':shared,'edge-domain.example.json':configure_edge(shared,c),
        'certificate-frontend.example.json':certificate_template([c['FRONTEND_DOMAIN']],c['ROUTE53_HOSTED_ZONE_ID']),
        'certificate-api.example.json':certificate_template([c['API_DOMAIN']],c['ROUTE53_HOSTED_ZONE_ID']),
        'api-domain.example.json':api_template(c,'api123'),'shared-routing.example.json':dns_template(c,'example.cloudfront.net')}
    folder=ROOT/'infra/hosting';folder.mkdir(exist_ok=True)
    for name,t in files.items():
        t['Description']='ILLUSTRATIVE ONLY: generate a native inventory and reviewed plan before deployment.'
        (folder/name).write_text(json.dumps(t,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return sorted(files)

if __name__=='__main__':print(json.dumps({'mode':'EXAMPLES_ONLY','files':generate()}))
