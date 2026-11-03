"""Admin-authored global notices; static publication and email use the existing sweep.

No lifecycle/admission switch: a notice never stops customer infrastructure.
Only an explicit, preview-bound admin command can publish or withdraw a notice.
"""
from copy import deepcopy
import hashlib
import json
import re
from .errors import HubError
from .service import ident, record, expected, retry
from .quotes import fingerprint

PUBLIC_KEY='S#MAINTENANCE_PUBLIC'
KINDS={'SCHEDULED','EXTENDED','COMPLETED'}
LANGUAGES={'vi','en','ja','ko','zh-Hans','fr','de','es'}
CONTENT={'title','message','impact','starts_at','ends_at','language','notice_kind'}
PUBLIC_FIELDS=CONTENT|{'announcement_id','published_at','created_at','revision'}


def notice_id(owner, aid):
    return ident('announcement-',owner,aid)


def public_content(row):
    return {k:deepcopy(v) for k,v in row.items() if k in PUBLIC_FIELDS}


class Announcements:
    def __init__(self, service, publication_enabled=True):self.s,self.publication_enabled=service,publication_enabled

    def state(self):
        return self.s.store.get(PUBLIC_KEY) or {'pk':PUBLIC_KEY,'generation':0,'status':'PENDING',
            'desired_id':None,'published_id':None,'attempts':0,'lease_until':0}

    def get(self, aid):
        if not isinstance(aid,str) or not re.fullmatch(r'ann-[a-f0-9]{24}',aid):
            raise HubError('NOT_FOUND','Announcement not found.',404)
        row=self.s.store.get('A#'+aid)
        if not row or row.get('kind')!='announcement':raise HubError('NOT_FOUND','Announcement not found.',404)
        return row

    def validate(self, body):
        if set(body)!=CONTENT:raise HubError('INVALID_INPUT','Expected announcement content only.')
        for key,limit in [('title',120),('message',2000),('impact',800)]:
            value=body[key]
            if not isinstance(value,str) or not value.strip() or len(value)>limit or any(ord(c)<32 and c not in '\n\t' for c in value):
                raise HubError('INVALID_INPUT','Invalid announcement '+key+'.')
        if body['language'] not in LANGUAGES or body['notice_kind'] not in KINDS:
            raise HubError('INVALID_INPUT','Unsupported announcement language or kind.')
        if any(type(body[k]) is not int for k in ['starts_at','ends_at']) or not 0<body['starts_at']<body['ends_at']<4102444800:
            raise HubError('INVALID_INPUT','Expected UTC epoch seconds with end after start.')
        if body['ends_at']-body['starts_at']>31*86400:
            raise HubError('INVALID_INPUT','A maintenance window cannot exceed 31 days.')
        return {k:v.strip() if isinstance(v,str) else v for k,v in body.items()}

    def view(self,row):
        state=self.state()
        result=public_content(row)|{k:row.get(k) for k in ['status','operation_id','send_email','email_cursor','email_queue_done','email_queued_count']}
        result['public_status']=state['status'] if row['announcement_id'] in {state.get('desired_id'),state.get('changed_id')} else 'SYNCED'
        result['current']=state.get('published_id')==row['announcement_id'] and row['status']=='PUBLISHED'
        return result

    def listing(self):
        rows=sorted(self.s.store.scan_kind('announcement'),key=lambda r:r['created_at'],reverse=True)
        return {'items':[self.view(r) for r in rows[:100]],'truncated':len(rows)>100,'publication_enabled':self.publication_enabled,'public_state':{
            k:self.state().get(k) for k in ['status','generation','published_id','last_synced_at','attempts']}}

    def _old(self,actor,key,scope,body):
        pk,fp,old=self.s.idempotency(actor,key,'announcements/'+scope,body)
        return pk,fp,old

    def _audit(self,actor,aid,action,op):
        return record('announcement_audit',ident('audit-',op),actor,announcement_id=aid,action=action,created_at=int(self.s.clock()))

    def create(self,actor,key,body):
        content=self.validate(body)
        def commit():
            pk,fp,old=self._old(actor,key,'create',body)
            if old:return self.view(self.get(old['announcement_id']))
            aid=ident('ann-',pk);op=ident('announce-op-',pk)
            row=record('announcement',aid,actor,announcement_id=aid,revision=1,status='DRAFT',created_at=int(self.s.clock()),operation_id=op,**content)
            rows=[row,{'pk':pk,'fingerprint':fp,'announcement_id':aid},self._audit(actor,aid,'create',op)]
            self.s.store.commit(rows,expected(*rows));return self.view(self.get(aid))
        return retry(commit)

    def edit(self,actor,aid,key,body):
        if set(body)!=CONTENT|{'expected_revision'}:raise HubError('INVALID_INPUT','Expected content and revision.')
        content=self.validate({k:body[k] for k in CONTENT})
        def commit():
            pk,fp,old=self._old(actor,key,aid+'/edit',body)
            if old:return self.view(self.get(aid))
            row=self.get(aid);self._revision(row,body['expected_revision'])
            if row['status']!='DRAFT':raise HubError('ANNOUNCEMENT_IMMUTABLE','Publish a new update instead of editing a sent notice.',409)
            row.update(content,revision=row['revision']+1,updated_at=int(self.s.clock()))
            rows=[row,{'pk':pk,'fingerprint':fp,'announcement_id':aid},self._audit(actor,aid,'edit',ident('announce-op-',pk))]
            self.s.store.commit(rows,expected(*rows));return self.view(self.get(aid))
        return retry(commit)

    def _revision(self,row,value):
        if type(value) is not int or value!=row['revision']:
            raise HubError('STALE_REVISION','The announcement changed. Review it again.',409)

    def preview(self,actor,aid,body):
        if set(body)!={'expected_revision','send_email'} or type(body['send_email']) is not bool:
            raise HubError('INVALID_INPUT','Expected revision and email choice.')
        row=self.get(aid);self._revision(row,body['expected_revision'])
        if row['status']!='DRAFT':raise HubError('ANNOUNCEMENT_IMMUTABLE','This notice is no longer a draft.',409)
        now=int(self.s.clock());pid=ident('preview-',actor,aid,str(row['revision']),str(now),str(body['send_email']))
        from .notification_email import runtime_gateway
        if body['send_email'] and runtime_gateway() is None:
            raise HubError('NOTIFICATION_EMAIL_UNAVAILABLE','Email delivery is not enabled.',503)
        prefs=self.s.store.scan_kind('preference')
        eligible=sum(p.get('email_enabled') is True and p.get('maintenance_email') is True and p.get('email_status')=='CONFIRMED' for p in prefs)
        preview=record('announcement_preview',pid,actor,announcement_id=aid,revision=row['revision'],send_email=body['send_email'],
                       fingerprint=fingerprint(public_content(row)),expires_at=now+600,consumed=False)
        def commit():
            existing=self.s.store.get(preview['pk'])
            if not existing:self.s.store.commit([preview],expected(preview))
        retry(commit)
        return {'preview_id':pid,'expires_at':now+600,'announcement':self.view(row),'audience':'ALL_ACCOUNTS',
                'confirmed_email_opt_ins':eligible,'send_email':body['send_email'],
                'email_count_is_estimate':True,'no_infrastructure_action':True,'publication_enabled':self.publication_enabled}

    def publish(self,actor,aid,key,body):
        if set(body)!={'expected_revision','preview_id','confirm_publish'} or body['confirm_publish'] is not True:
            raise HubError('INVALID_INPUT','An explicit reviewed publication confirmation is required.')
        if not isinstance(body['preview_id'],str) or not re.fullmatch('preview-[a-f0-9]{24}',body['preview_id']):
            raise HubError('INVALID_INPUT','Invalid preview ID.')
        def commit():
            pk,fp,old=self._old(actor,key,aid+'/publish',body)
            if old:return self.view(self.get(aid))
            if not self.publication_enabled:raise HubError('ANNOUNCEMENT_PUBLIC_UNAVAILABLE','Static publication is not enabled.',503)
            row=self.get(aid);self._revision(row,body['expected_revision'])
            p=self.s.store.get('A#'+body['preview_id']);now=int(self.s.clock())
            if (not p or p.get('owner_id')!=actor or p.get('announcement_id')!=aid or p.get('consumed')
                or p.get('expires_at',0)<=now or p.get('revision')!=row['revision'] or p.get('fingerprint')!=fingerprint(public_content(row))):
                raise HubError('ANNOUNCEMENT_PREVIEW_REQUIRED','Review the current draft before publishing.',409)
            if row['status']!='DRAFT':raise HubError('ANNOUNCEMENT_IMMUTABLE','This draft was already accepted.',409)
            state=self.state();self._available(state)
            row.update(status='QUEUED',revision=row['revision']+1,send_email=p['send_email'],operation_id=ident('announce-op-',pk),
                       requested_at=now,email_queued_count=0,email_queue_done=not p['send_email'])
            state.update(generation=state['generation']+1,status='PENDING',desired_id=aid,changed_id=aid,attempts=0,retry_after=0)
            p['consumed']=True
            rows=[row,state,p,{'pk':pk,'fingerprint':fp,'announcement_id':aid},self._audit(actor,aid,'publish',row['operation_id'])]
            self.s.store.commit(rows,expected(*rows));return self.view(self.get(aid))
        return retry(commit)

    def _available(self,state):
        if state.get('lease_until',0)>self.s.clock() or state['status'] not in {'SYNCED','PENDING'} or state.get('changed_id'):
            raise HubError('ANNOUNCEMENT_BUSY','A public notice update needs synchronization or retry first.',409)

    def cancel(self,actor,aid,key,body):
        if set(body)!={'expected_revision','confirm_cancel'} or body['confirm_cancel'] is not True:
            raise HubError('INVALID_INPUT','Expected explicit withdrawal confirmation and revision.')
        def commit():
            pk,fp,old=self._old(actor,key,aid+'/cancel',body)
            if old:return self.view(self.get(aid))
            row=self.get(aid);self._revision(row,body['expected_revision']);state=self.state()
            if state.get('lease_until',0)>self.s.clock():raise HubError('ANNOUNCEMENT_BUSY','Public synchronization is running.',409)
            if row['status']=='DRAFT':row['status']='CANCELLED';rows=[row]
            else:
                if aid not in {state.get('published_id'),state.get('desired_id')}:
                    raise HubError('ANNOUNCEMENT_NOT_CURRENT','Only the current or pending notice can be withdrawn.',409)
                if state.get('changed_id') not in (None,aid):raise HubError('ANNOUNCEMENT_BUSY','Another update is pending.',409)
                target=None if state.get('published_id')==aid else state.get('published_id')
                row['status']='CANCEL_PENDING'
                state.update(generation=state['generation']+1,status='PENDING',desired_id=target,changed_id=aid,attempts=0,retry_after=0)
                rows=[row,state]
            row.update(revision=row['revision']+1,operation_id=ident('announce-op-',pk))
            rows += [{'pk':pk,'fingerprint':fp,'announcement_id':aid},self._audit(actor,aid,'cancel',row['operation_id'])]
            self.s.store.commit(rows,expected(*rows));return self.view(self.get(aid))
        return retry(commit)

    def retry_sync(self,actor,aid,key,body):
        if set(body)!={'expected_revision'}:raise HubError('INVALID_INPUT','Expected revision only.')
        def commit():
            pk,fp,old=self._old(actor,key,aid+'/retry',body)
            if old:return self.view(self.get(aid))
            row=self.get(aid);self._revision(row,body['expected_revision']);state=self.state()
            if state.get('changed_id')!=aid or state['status']!='FAILED' or state.get('lease_until',0)>self.s.clock():
                raise HubError('ANNOUNCEMENT_RETRY_UNAVAILABLE','Only a failed public synchronization can be retried.',409)
            state.update(status='PENDING',attempts=0,retry_after=0)
            row.update(operation_id=ident('announce-op-',pk),revision=row['revision']+1)
            rows=[row,state,{'pk':pk,'fingerprint':fp,'announcement_id':aid},self._audit(actor,aid,'retry',row['operation_id'])]
            self.s.store.commit(rows,expected(*rows));return self.view(self.get(aid))
        return retry(commit)

    def sync_public(self,writer):
        """Bounded, recoverable CAS publication. Never report success on S3 timeout."""
        now=int(self.s.clock());token=ident('lease-',writer.token(),str(now))
        def claim():
            state=self.state()
            if state['status']=='SYNCED' or state['status']=='FAILED' or state.get('retry_after',0)>now or state.get('lease_until',0)>now:return None
            state.update(status='SYNCING',lease_token=token,lease_until=now+60,attempts=state.get('attempts',0)+1)
            self.s.store.commit([state],expected(state));return self.state()
        state=retry(claim)
        if not state:return None
        aid=state.get('desired_id');row=self.get(aid) if aid else None
        payload={'schema':1,'publisher':'cloudhub-maintenance','generation':int(state['generation']),'active':bool(row),
                 'announcement':public_content(row) if row else None}
        payload['generated_at']=now
        def still_current():
            fresh=self.state()
            return fresh.get('lease_token')==token and fresh['generation']==state['generation'] and fresh.get('lease_until',0)>self.s.clock()
        try:
            result=writer.write(payload,still_current)
            if not result:raise RuntimeError('Public synchronization was superseded')
        except Exception:
            def failed():
                fresh=self.state()
                if fresh.get('lease_token')!=token:return
                fresh.update(status='FAILED' if fresh['attempts']>=3 else 'PENDING',retry_after=int(self.s.clock())+300,lease_until=0,last_error='PUBLIC_SYNC_FAILED')
                self.s.store.commit([fresh],expected(fresh))
            retry(failed);return {'status':'PUBLIC_SYNC_FAILED','generation':int(state['generation'])}
        def complete():
            fresh=self.state()
            if fresh.get('lease_token')!=token or fresh['generation']!=state['generation']:return None
            rows=[fresh];changed=self.get(fresh['changed_id']) if fresh.get('changed_id') else None
            if changed:
                changed.update(status='CANCELLED' if changed['status']=='CANCEL_PENDING' else 'PUBLISHED')
                if changed['status']=='PUBLISHED':changed['published_at']=now
                rows.append(changed)
            fresh.update(status='SYNCED',published_id=aid,changed_id=None,lease_until=0,last_synced_at=now,public_sha256=result['sha256'])
            self.s.store.commit(rows,expected(*rows));return {'status':'SYNCED','generation':int(state['generation']),'sha256':result['sha256']}
        return retry(complete)

    def virtual(self,owner):
        """Global inbox delivery is lazy, so publication does not scan all users."""
        state=self.state();rows=[]
        for row in self.s.store.scan_kind('announcement'):
            if row.get('published_at'):
                rows.append(self.notification(owner,row,state.get('published_id')==row['announcement_id'] and row['status']=='PUBLISHED'))
        return rows

    def notification(self,owner,row,current=True):
        fields=public_content(row)|{'notification_id':notice_id(owner,row['announcement_id']),'type':'MAINTENANCE_NOTICE',
            'created_at':row['published_at'],'read_at':None,'email_status':'NOT_REQUESTED'}
        return record('notification',fields['notification_id'],owner,**fields)

    def current(self,item):
        state=self.state();row=self.s.store.get('A#'+item.get('announcement_id',''))
        return bool(row and row['status']=='PUBLISHED' and state.get('published_id')==row['announcement_id'])

    def email_current(self,item):
        return self.current(item) and self.state().get('desired_id')==item['announcement_id']

    def queue_emails(self,limit=10):
        state=self.state();aid=state.get('published_id')
        if not aid or state.get('desired_id')!=aid:return 0
        row=self.get(aid)
        if row['status']!='PUBLISHED' or not row.get('send_email') or row.get('email_queue_done'):return 0
        prefs=sorted(self.s.store.scan_kind('preference'),key=lambda p:p['owner_id'])
        candidates=[p for p in prefs if p['owner_id']>row.get('email_cursor','')][:limit]
        count=0
        for pref in candidates:
            def commit():
                fresh=self.get(aid)
                if fresh.get('email_cursor','')>=pref['owner_id']:return False
                if not self.email_current({'announcement_id':aid}):return False
                current_pref=self.s.store.get(pref['pk']) or {};rows=[fresh]
                if (current_pref.get('email_enabled') is True and current_pref.get('maintenance_email') is True
                    and current_pref.get('maintenance_email_enabled_since',0)<=row['published_at']):
                    n=self.notification(pref['owner_id'],row);existing=self.s.store.get(n['pk'])
                    if existing:n=existing
                    if not n.get('maintenance_email_queued'):
                        n.update(email_status='PENDING',maintenance_email_queued=True)
                        rows.append(n);fresh['email_queued_count']=fresh.get('email_queued_count',0)+1
                fresh['email_cursor']=pref['owner_id'];self.s.store.commit(rows,expected(*rows));return len(rows)>1
            count+=bool(retry(commit))
        def finish():
            fresh=self.get(aid)
            if not any(p['owner_id']>fresh.get('email_cursor','') for p in prefs):
                fresh['email_queue_done']=True;self.s.store.commit([fresh],expected(fresh))
        retry(finish);return count


class StaticNoticeWriter:
    def __init__(self,client,bucket,account):
        if not re.fullmatch(r'\d{12}',account) or not bucket:raise ValueError('Explicit owned frontend bucket required')
        self.client,self.bucket,self.account=client,bucket,account
    def token(self):
        import secrets
        return secrets.token_hex(12)
    def write(self,payload,still_current):
        from botocore.exceptions import ClientError
        data=json.dumps(payload,sort_keys=True,separators=(',',':'),ensure_ascii=False,default=lambda v:int(v)).encode('utf-8')
        if len(data)>16384:raise ValueError('Public maintenance payload too large')
        args={'Bucket':self.bucket,'Key':'maintenance.json','ExpectedBucketOwner':self.account,'Body':data,
            'ContentType':'application/json; charset=utf-8','CacheControl':'no-store, max-age=0, must-revalidate','ServerSideEncryption':'AES256'}
        if not still_current():return None
        try:
            # Initial publication does not require ListBucket to distinguish 403
            # from a missing key. Existing objects are never overwritten blindly.
            self.client.put_object(**args,IfNoneMatch='*')
        except ClientError as exc:
            if exc.response['Error']['Code'] not in {'PreconditionFailed','412'}:raise
            obj=self.client.get_object(Bucket=self.bucket,Key='maintenance.json',ExpectedBucketOwner=self.account)
            previous=obj['Body'].read(16385);obj['Body'].close()
            if len(previous)>16384 or json.loads(previous).get('publisher')!='cloudhub-maintenance':
                raise ValueError('Existing key is not a CloudHub maintenance document')
            if not still_current():return None
            self.client.put_object(**args,IfMatch=obj['ETag'])
        return {'sha256':hashlib.sha256(data).hexdigest()}


def runtime_writer():
    import os
    if os.getenv('MAINTENANCE_PUBLIC_ENABLED','false').lower()!='true':return None
    import boto3
    from botocore.config import Config
    return StaticNoticeWriter(boto3.client('s3',config=Config(connect_timeout=.4,read_timeout=1.5,retries={'total_max_attempts':1})),
        os.environ['MAINTENANCE_FRONTEND_BUCKET'],os.environ['NOTIFICATION_ACCOUNT_ID'])
