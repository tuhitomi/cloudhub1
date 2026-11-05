"""Bounded measurement primitives, NEVER callable through the product API.

The operator runner validates an isolated CloudHub environment and reviewed
budget before calling these functions. Results are raw observations, not capacity
claims. The hash of this module versions the executable measurement scenario.
"""
import concurrent.futures,hashlib,json,os,pathlib,time,urllib.request,urllib.parse,urllib.error

def revision():
    # Ship this small index with Lambda too. Changes to the runner or k6
    # scenario invalidate past evidence even though those tools run off Lambda.
    sources=json.loads(pathlib.Path(__file__).with_name('benchmark-scenarios.json').read_text(encoding='utf-8'))
    if sources.get('agent')!=hashlib.sha256(pathlib.Path(__file__).read_text(encoding='utf-8').encode()).hexdigest():raise ValueError('Regenerate benchmark scenario source index')
    return hashlib.sha256(json.dumps(sources,sort_keys=True,separators=(',',':')).encode()).hexdigest()

class SameOriginRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        before=urllib.parse.urlsplit(req.full_url);after=urllib.parse.urlsplit(newurl)
        if after.hostname!=before.hostname or after.port!=before.port or after.scheme not in {'http','https'} or before.scheme=='https' and after.scheme!='https':
            raise ValueError('Redirect outside approved test origin')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def classify_cache(observations):
    states={('MISS' if 'Miss from cloudfront' in str(v.get('x_cache')) else 'HIT' if 'Hit from cloudfront' in str(v.get('x_cache')) else 'UNKNOWN') for v in observations}
    return 'UNKNOWN' if not states or 'UNKNOWN' in states else 'MIXED' if len(states)>1 else 'COLD' if states=={'MISS'} else 'WARM'

def bounded_arrival(probe,duration_s,rate,max_concurrency,warmup_s=0,*,on_measurement_start=None):
    if not all(type(n) is int for n in [duration_s,rate,max_concurrency,warmup_s]) or not 1<=duration_s<=3600 or not 1<=rate<=100 or not 1<=max_concurrency<=16 or rate*duration_s>10000 or not 0<=warmup_s<=duration_s:raise ValueError('Unreviewed measurement bounds')
    warm_end=time.monotonic()+warmup_s
    while time.monotonic()<warm_end:probe();time.sleep(1/rate)
    if on_measurement_start:on_measurement_start()
    samples=[];dropped=0;started=int(time.time());clock=time.monotonic();pending=set();stopped=False
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrency) as pool:
        for i in range(duration_s*rate):
            wait=clock+i/rate-time.monotonic()
            if wait>0:time.sleep(wait)
            done={f for f in pending if f.done()}
            for future in done:samples.append(future.result())
            pending-=done
            # Do not queue excess work and mistake an underpowered generator for
            # a successfully achieved arrival rate.
            if len(pending)>=max_concurrency:dropped+=1;continue
            if len(samples)>=10 and sum(not(s['ok'] and s['correct']) for s in samples)*100>len(samples)*10:stopped=True;break
            pending.add(pool.submit(probe))
        for future in concurrent.futures.as_completed(pending):samples.append(future.result())
        remaining=clock+duration_s-time.monotonic()
        if remaining>0 and not stopped:time.sleep(remaining)
    ended=max(started+1,int(time.time()))
    return {'samples':samples,'execution':{'started_at':started,'ended_at':ended,'duration_s':ended-started,'warmup_s':warmup_s,'target_rate':rate,
        'dropped_iterations':dropped,'stop_reason':'ERROR_BUDGET' if stopped else 'GENERATOR_LIMIT' if dropped else 'COMPLETED'}}

def http_probe(target,expected_sha256,*,token=None,maximum_bytes=5*1024*1024,pops=None,cache_observations=None):
    parsed=urllib.parse.urlsplit(target)
    if parsed.scheme not in {'http','https'} or parsed.username or parsed.password or parsed.query or parsed.fragment:raise ValueError('Target must be an approved origin/path without credentials or query')
    if not isinstance(expected_sha256,str) or len(expected_sha256)!=64:raise ValueError('An expected content SHA-256 is required')
    def probe():
        start=time.perf_counter();correct=False;ok=False;size=0
        try:
            headers={'User-Agent':'CloudHub-Isolated-Benchmark/1'}
            if token:
                if parsed.scheme!='https':raise ValueError('Bearer token requires HTTPS')
                headers['Authorization']='Bearer '+token
            request=urllib.request.Request(target,headers=headers)
            with urllib.request.build_opener(SameOriginRedirect()).open(request,timeout=5) as response:
                body=response.read(maximum_bytes+1);size=len(body);ok=response.status==200 and size<=maximum_bytes
                correct=ok and hashlib.sha256(body).hexdigest()==expected_sha256
                if pops is not None and response.headers.get('X-Amz-Cf-Pop'):pops.add(response.headers['X-Amz-Cf-Pop'])
                if cache_observations is not None:cache_observations.append({'pop':response.headers.get('X-Amz-Cf-Pop'),'x_cache':response.headers.get('X-Cache')})
        except Exception:pass  # No request/header/body/credential is logged.
        return {'elapsed_ms':(time.perf_counter()-start)*1000,'ok':ok,'bytes':size if ok else 0,'correct':correct}
    return probe

def io_probe(root,nonce,block_bytes=4096):
    if root not in {'/data','/shared'} or not __import__('re').fullmatch('[a-f0-9]{24}',nonce) or not 1<=block_bytes<=1048576:raise ValueError('Invalid isolated I/O scope')
    base=pathlib.Path(root)/'.cloudhub-bench'
    if base.is_symlink():raise ValueError('Unsafe benchmark directory')
    base.mkdir(exist_ok=True);folder=base/nonce;folder.mkdir(exist_ok=False)
    payload=hashlib.sha256(nonce.encode()).digest()*(block_bytes//32+1);payload=payload[:block_bytes];expected=hashlib.sha256(payload).hexdigest();owned=[]
    def probe():
        start=time.perf_counter();path=folder/os.urandom(8).hex();ok=correct=False
        try:
            with path.open('xb') as f:f.write(payload);f.flush();os.fsync(f.fileno())
            owned.append(path);correct=hashlib.sha256(path.read_bytes()).hexdigest()==expected;ok=True
        except Exception:pass
        return {'elapsed_ms':(time.perf_counter()-start)*1000,'ok':ok,'bytes':len(payload)*2 if ok else 0,'correct':correct}
    def cleanup():
        for path in owned:
            if path.parent!=folder or path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise ValueError('I/O data changed; preserve probe source')
            path.unlink()
        folder.rmdir()
    return probe,cleanup,{'sha256':expected,'block_bytes':block_bytes,'pattern':'unique-file write/fsync/readback; not arbitrary workload IOPS','path':str(folder)}

def cpu_probe():
    payload=b'cloudhub-isolated-cpu-reference-v1'*1024;expected=hashlib.sha256(payload).hexdigest()
    def probe():
        start=time.perf_counter();correct=hashlib.sha256(payload).hexdigest()==expected
        return {'elapsed_ms':(time.perf_counter()-start)*1000,'ok':True,'bytes':len(payload),'correct':correct}
    return probe

def shared_marker(nonce,index,action):
    """Cross-client EFS check, confined to unique checksum-bound probe files."""
    import re
    if not re.fullmatch('[a-f0-9]{24}',nonce) or index not in {0,1} or action not in {'create','read','cleanup'}:raise ValueError('Invalid shared marker scope')
    root=pathlib.Path('/shared/.cloudhub-bench')
    if root.is_symlink():raise ValueError('Unsafe shared probe directory')
    root.mkdir(exist_ok=True);path=root/('marker-'+nonce+'-'+str(index));data=('cloudhub-cross-node-v1:'+nonce+':'+str(index)).encode();sha=hashlib.sha256(data).hexdigest()
    if path.is_symlink():raise ValueError('Unsafe shared marker')
    if action=='create':
        with path.open('xb') as f:f.write(data);f.flush();os.fsync(f.fileno())
    if hashlib.sha256(path.read_bytes()).hexdigest()!=sha:raise ValueError('Cross-client checksum mismatch; preserve source')
    if action=='cleanup':path.unlink()
    return {'marker':index,'action':action,'sha256':sha,'correct':True}

def remote_marker_script(nonce,index,action):
    import base64
    # Validate before constructing the command as well as on the target.
    if not __import__('re').fullmatch('[a-f0-9]{24}',nonce) or index not in {0,1} or action not in {'create','read','cleanup'}:raise ValueError('Invalid marker command')
    encoded=base64.b64encode(pathlib.Path(__file__).read_bytes()).decode()
    return "python3 - <<'CLOUDHUB_MARKER'\nimport base64,json\nns={}\nexec(compile(base64.b64decode("+repr(encoded)+"),'cloudhub-benchmark-agent','exec'),ns)\nprint(json.dumps(ns['shared_marker']("+repr(nonce)+','+str(index)+','+repr(action)+")))\nCLOUDHUB_MARKER"

def s3_probe(client,bucket,account,nonce,maximum_file_bytes):
    if not __import__('re').fullmatch('[a-f0-9]{24}',nonce):raise ValueError('Invalid isolated object namespace')
    # One new object only. No overwrite or deletion outside this exact key and
    # version. Download results are checked against generated payload bytes.
    key='benchmark-'+nonce+'/probe.bin';seed=b'CloudHub S3 reference v1\n';size=min(maximum_file_bytes,5*1024*1024);payload=(seed*((size+len(seed)-1)//len(seed)))[:size]
    response=client.put_object(Bucket=bucket,Key=key,Body=payload,IfNoneMatch='*',ExpectedBucketOwner=account,ServerSideEncryption='AES256')
    version=response.get('VersionId');expected=hashlib.sha256(payload).hexdigest()
    def probe():
        start=time.perf_counter();ok=correct=False;size=0
        try:
            args={'Bucket':bucket,'Key':key,'ExpectedBucketOwner':account}
            if version:args['VersionId']=version
            data=client.get_object(**args)['Body'].read(len(payload)+1);size=len(data);ok=size==len(payload);correct=ok and hashlib.sha256(data).hexdigest()==expected
        except Exception:pass
        return {'elapsed_ms':(time.perf_counter()-start)*1000,'ok':ok,'bytes':size,'correct':correct}
    def cleanup():
        args={'Bucket':bucket,'Key':key,'ExpectedBucketOwner':account}
        if version:args['VersionId']=version
        client.delete_object(**args)
    return probe,cleanup,{'key':key,'version_id':version,'sha256':expected,'bytes':len(payload),'scope':'single conditional PUT then checksum-verified S3 GETs; not the CloudHub upload API'}

def remote_io_script(root,nonce,duration_s,rate,concurrency,task='io'):
    import base64
    encoded=base64.b64encode(pathlib.Path(__file__).read_bytes()).decode()
    if task not in {'cpu','io'}:raise ValueError('Unsupported reference task')
    setup="p=ns['cpu_probe']();c=lambda:None;scope={'scope':'fixed SHA-256 CPU job, not arbitrary software capacity'}" if task=='cpu' else "p,c,scope=ns['io_probe']("+repr(root)+','+repr(nonce)+")"
    return "python3 - <<'CLOUDHUB_BENCH'\nimport base64,json\nns={}\nexec(compile(base64.b64decode("+repr(encoded)+"),'cloudhub-benchmark-agent','exec'),ns)\n"+setup+"\ntry:\n result=ns['bounded_arrival'](p,"+str(duration_s)+','+str(rate)+','+str(concurrency)+")\n result['scope']=scope\n print(json.dumps(result))\nfinally:c()\nCLOUDHUB_BENCH"
