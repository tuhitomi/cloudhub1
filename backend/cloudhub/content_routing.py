"""Immutable public release URLs. No cache invalidations or origin-path switch."""
import json
import re
from .errors import HubError

PUBLIC_PREFIX = '/_cloudhub_site/'


def routing_code(active='initial', published=('initial',)):
    ids=sorted(set(published))
    if active not in ids or len(ids)>4 or any(not re.fullmatch(r'initial|release-[a-f0-9]{24}',v) for v in ids):
        raise HubError('PUBLICATION_CONFLICT','Invalid published release routing.',409)
    return ('var active='+json.dumps(active)+';var published='+json.dumps(ids)+';'+r"""
function handler(e){
 var r=e.request,u=r.uri;
 function deny(){return {statusCode:403,statusDescription:'Forbidden',headers:{'cache-control':{value:'no-store'}}};}
 try{u=decodeURIComponent(decodeURIComponent(u));}catch(x){return deny();}
 if(u.indexOf('%')!==-1||u.indexOf('\\')!==-1||/(^|\/)\.\.?($|\/)/.test(u)||/[\x00-\x1f]/.test(u))return deny();
 if(/(^|\/)\.cloudhub(\/|$)/.test(u))return u==='/.cloudhub/ready.txt'?r:deny();
 var prefix='/_cloudhub_site/';
 if(u.indexOf(prefix)===0){
  var tail=u.slice(prefix.length),split=tail.indexOf('/'),id=tail.slice(0,split),path=tail.slice(split+1);
  if(split<1||published.indexOf(id)<0||/(^|\/)\.cloudhub(\/|$)/.test(path))return deny();
  r.uri=(id==='initial'?'/':'/.cloudhub/releases/'+id+'/')+(path||'index.html');return r;
 }
 // Unversioned assets are rejected rather than silently mixing releases.
 if(u!=='/'&&!/\.html$/.test(u))return deny();
 var query=[],q=r.querystring||{};
 for(var k in q){var vs=q[k].multiValue||[q[k]];for(var j=0;j<vs.length;j++)query.push(encodeURIComponent(k)+'='+encodeURIComponent(vs[j].value));}
 return {statusCode:302,statusDescription:'Found',headers:{location:{value:prefix+active+(u==='/'?'/index.html':u)+(query.length?'?'+query.join('&'):'')},'cache-control':{value:'no-store, max-age=0'}}};
}
""").strip()


def validate_links(data, content_type, file_key='content'):
    """The supported static-site contract uses relative local asset URLs.

    This is a conservative preflight, not a JavaScript program analyser. The
    edge guard also rejects unversioned assets generated dynamically at runtime.
    """
    if any(t in content_type for t in ['html','css','javascript']):
        text=data.decode('utf-8',errors='strict')
        reference=re.search(r'''(?:["'`(=]\s*)(/(?!/)[^"'`\s)<>]{0,160})''',text)
        if reference or re.search(r'<base\b',text,re.I):
            path=reference.group(1).split('?',1)[0].split('#',1)[0][:128] if reference else '<base>'
            raise HubError('RELEASE_UNVERSIONED_REFERENCE','Use relative local asset URLs and omit base tags.',409,
                details={'file':file_key,'asset_path':path})

