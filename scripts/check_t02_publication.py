"""Read-only observer for A/warm/B/rollback checks, not a publishing command."""
import argparse,hashlib,json,re,urllib.request,urllib.error
from pathlib import Path
from datetime import datetime,timezone

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None

def observe(origin,manifest,previous=None,warm=2,fetch=None):
    if not re.fullmatch(r'https://[a-z0-9]+\.cloudfront\.net',origin):raise ValueError('Use the owned workload CloudFront HTTPS origin, without a path')
    def get(path,limit):
        try:r=urllib.request.build_opener(NoRedirect).open(origin+path,timeout=15)
        except urllib.error.HTTPError as exc:r=exc
        with r:return r.status,{k.lower():v for k,v in r.headers.items()},r.read(limit+1)
    fetch=fetch or get;results=[]
    active=manifest['release_id'];prefix='/_cloudhub_site/'+active+'/'
    if not re.fullmatch(r'initial|release-[a-f0-9]{24}',active):raise ValueError('Invalid release ID')
    status,headers,_=fetch('/',0)
    results.append({'path':'/','status':status,'location':headers.get('location'),
                    'passed':status==302 and headers.get('location')==prefix+'index.html' and 'no-store' in headers.get('cache-control','')})
    for cohort in [manifest]+([previous] if previous else []):
        rid=cohort['release_id']
        if not re.fullmatch(r'initial|release-[a-f0-9]{24}',rid) or not 1<=len(cohort['files'])<=100:raise ValueError('Invalid manifest')
        for item in cohort['files']:
            key=item['key'];size=int(item['size'])
            if not re.fullmatch(r'[A-Za-z0-9_.\-/]{1,128}',key) or any(s in {'','..','.','.cloudhub'} for s in key.split('/')) or not 0<size<=5242880:raise ValueError('Invalid public file bounds')
            if not re.fullmatch(r'[a-f0-9]{64}',item['sha256']):raise ValueError('Invalid SHA-256')
            path='/_cloudhub_site/'+rid+'/'+key
            for attempt in range(warm):
                status,h,data=fetch(path,size);digest=hashlib.sha256(data).hexdigest()
                results.append({'path':path,'attempt':attempt+1,'status':status,'bytes':len(data),'sha256':digest,
                    'cloudfront_pop':h.get('x-amz-cf-pop'),'cache':h.get('x-cache'),'age':h.get('age'),
                    'passed':status==200 and len(data)==size and digest==item['sha256']})
    # No public namespace can access draft bytes even if the S3 key is guessed.
    for path in ['/.cloudhub/releases/not-published/index.html','/_cloudhub_site/release-'+'f'*24+'/index.html','/app.js']:
        status,h,_=fetch(path,1024);results.append({'path':path,'status':status,'passed':status==403})
    return {'recorded_at':datetime.now(timezone.utc).isoformat(),'mode':'PUBLIC_HTTP_READ_ONLY','origin':origin,
        'active_release':active,'passed':all(r['passed'] for r in results),'checks':results,'aws_mutations':0,
        'limits':['Only the observer network/POPs reached are measured; no simultaneous global cutover guarantee.',
                  'GET/checksums verify bytes, not execution of arbitrary user JavaScript or every browser cache.',
                  'Run separately after A, B and rollback A; this tool does not create, publish, restore or clean up resources.']}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--origin',required=True);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--previous-manifest',type=Path);p.add_argument('--warm-repeat',type=int,default=2);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if not 1<=a.warm_repeat<=3:p.error('Use 1–3 warm requests per object')
    result=observe(a.origin.rstrip('/'),json.loads(a.manifest.read_text()),json.loads(a.previous_manifest.read_text()) if a.previous_manifest else None,a.warm_repeat)
    a.out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps({'passed':result['passed'],'checks':len(result['checks']),'aws_mutations':0}));return 0 if result['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
