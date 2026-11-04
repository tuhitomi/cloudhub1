"""One compact reviewed global document, expanded without changing origin Region."""
from copy import deepcopy
def apply(rates,document):
    out=deepcopy(rates);keys={'cloudfront_transfer_gib','cloudfront_requests_10000'}
    if document.get('approved') is not True or document.get('price_class')!='PriceClass_100' or not keys<=document.get('units',{}).keys() or not document.get('updated_at'):
        for key in keys:out.get('units',{}).pop(key,None)
        out['cloudfront_viewer_rates']={};out['cloudfront_pricing_unavailable']=True;return out
    out['units'].update(document['units'])
    out['cloudfront_viewer_rates']={scope:{k:v for k,v in document.items() if k!='viewers'} for scope in document.get('viewers',[]) if scope in {'US','EU','APAC','OTHER'}}
    out['cloudfront_price_document_version']=document.get('price_version');return out
