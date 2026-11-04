"""Country-only public context. Direct API requests cannot supply trusted geography."""
import hmac
import re
from .errors import HubError

LOCALES=('vi','en','ja','ko','zh-Hans','fr','de','es')
COUNTRIES={'VN':'vi','JP':'ja','KR':'ko','CN':'zh-Hans','FR':'fr','DE':'de','ES':'es'}

def locale_for_country(country):return COUNTRIES.get(country,'en')

def context(event,secret):
    headers={k.lower():v for k,v in event.get('headers',{}).items()}
    supplied=headers.get('x-cloudhub-edge-key','')
    trusted=isinstance(secret,str) and len(secret)>=32 and isinstance(supplied,str) and hmac.compare_digest(secret,supplied)
    country=headers.get('cloudfront-viewer-country') if trusted else None
    if not isinstance(country,str) or not re.fullmatch('[A-Z]{2}',country):country=None
    return {'country_code':country,'suggested_language':locale_for_country(country),'supported_languages':list(LOCALES),
            'source':'cloudfront' if trusted else 'unavailable','default_language':'en'}

def preference(service,owner,body,request_epoch=None):
    from .service import expected,retry
    if set(body)!={'language'} or body['language'] not in (*LOCALES,'auto'):
        raise HubError('INVALID_LANGUAGE','Choose a supported language or automatic location selection.')
    request_epoch=int(request_epoch if request_epoch is not None else service.clock()*1000)
    def save():
        row=service.store.get('U#'+owner)
        if not row:raise HubError('NOT_FOUND','Account profile is not available.',404)
        if request_epoch<int(row.get('language_request_epoch',0)):
            return {'language_preference':row.get('language_preference','auto')}
        row['language_preference']=body['language']
        row['language_request_epoch']=request_epoch
        service.store.commit([row],expected(row))
        return {'language_preference':row['language_preference']}
    return retry(save)
