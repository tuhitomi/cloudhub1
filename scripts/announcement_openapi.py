"""Maintenance notices: admin-authored drafts, preview and explicit asynchronous publish."""
def extend(doc):
    schemas=doc['components']['schemas'];ref=lambda x:{'$ref':'#/components/schemas/'+x}
    content={'title':{'type':'string','minLength':1,'maxLength':120},'message':{'type':'string','minLength':1,'maxLength':2000},
        'impact':{'type':'string','minLength':1,'maxLength':800},'starts_at':{'type':'integer','description':'UTC Unix seconds'},
        'ends_at':{'type':'integer','description':'Expected end, not automatic completion. Window at most 31 days.'},
        'language':{'type':'string','enum':['vi','en','ja','ko','zh-Hans','fr','de','es']},
        'notice_kind':{'type':'string','enum':['SCHEDULED','EXTENDED','COMPLETED']}}
    schemas['AnnouncementContent']={'type':'object','additionalProperties':False,'required':list(content),'properties':content}
    schemas['AnnouncementEdit']={'type':'object','additionalProperties':False,'required':list(content)+['expected_revision'],
        'properties':dict(content,expected_revision={'type':'integer','minimum':1})}
    schemas['Announcement']={'type':'object','properties':dict(content,announcement_id={'type':'string'},revision={'type':'integer'},
        status={'type':'string','enum':['DRAFT','QUEUED','PUBLISHED','CANCEL_PENDING','CANCELLED']},operation_id={'type':'string'},
        public_status={'type':'string','enum':['PENDING','SYNCING','SYNCED','FAILED']},current={'type':'boolean'},email_queued_count={'type':'integer'})}
    schemas['AnnouncementPreviewInput']={'type':'object','additionalProperties':False,'required':['expected_revision','send_email'],
        'properties':{'expected_revision':{'type':'integer'},'send_email':{'type':'boolean'}}}
    schemas['AnnouncementPublishInput']={'type':'object','additionalProperties':False,'required':['expected_revision','preview_id','confirm_publish'],
        'properties':{'expected_revision':{'type':'integer'},'preview_id':{'type':'string'},'confirm_publish':{'type':'boolean','enum':[True]}}}
    schemas['AnnouncementCancelInput']={'type':'object','additionalProperties':False,'required':['expected_revision','confirm_cancel'],
        'properties':{'expected_revision':{'type':'integer'},'confirm_cancel':{'type':'boolean','enum':[True]}}}
    schemas['AnnouncementRetryInput']={'type':'object','additionalProperties':False,'required':['expected_revision'],'properties':{'expected_revision':{'type':'integer'}}}
    props=schemas['Notification']['properties'];props.update(content,announcement_id={'type':'string'})
    security=doc['paths']['/admin/notifications']['get']['security']
    from announcement_infra import ROUTES
    for method,path in ROUTES:
        action=path.rsplit('/',1)[-1];body=None
        if method=='PUT':body='AnnouncementEdit'
        elif method=='POST':body={'preview':'AnnouncementPreviewInput','publish':'AnnouncementPublishInput','cancel':'AnnouncementCancelInput','retry':'AnnouncementRetryInput'}.get(action,'AnnouncementContent')
        code='202' if action in ['publish','cancel','retry'] else '201' if method=='POST' and path=='/admin/announcements' else '200'
        op={'operationId':'maintenance'+method+path.replace('/','_').replace('{announcement_id}','ById'),'security':security,
            'description':'Live Cognito admin revalidation. Does not stop infrastructure. Public synchronization is asynchronous; SYNCED is S3 acceptance, not all POPs or inbox delivery.',
            'responses':{code:{'description':'Accepted/OK; long commands return operation_id','content':{'application/json':{'schema':ref('Announcement') if action not in ['preview','announcements'] else {'type':'object'}}}},
                **{status:{'description':text,'content':{'application/json':{'schema':ref('Error')}}} for status,text in [('400','Invalid input'),('401','JWT required'),('403','Live admin group required'),('404','Not found'),('409','Stale revision, preview or synchronization busy'),('503','Static publication/email not enabled')]}}}
        if '{announcement_id}' in path:op['parameters']=[{'name':'announcement_id','in':'path','required':True,'schema':{'type':'string','pattern':'^ann-[a-f0-9]{24}$'}}]
        if body:op['requestBody']={'required':True,'content':{'application/json':{'schema':ref(body)}}}
        if method in ['POST','PUT'] and action!='preview':op.setdefault('parameters',[]).append({'name':'Idempotency-Key','in':'header','required':True,'schema':{'type':'string'}})
        doc['paths'].setdefault(path,{})[method.lower()]=op
