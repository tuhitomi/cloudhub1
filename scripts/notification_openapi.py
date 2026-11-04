"""Notification schema v2 is additive; old clients retain their type subset."""
def extend(doc):
    schemas=doc['components']['schemas'];ref=lambda name:{'$ref':'#/components/schemas/'+name}
    nullable_time={'type':'integer','nullable':True,'description':'Unix seconds; null means not recorded.'}
    schemas['Notification']={'type':'object','required':['notification_id','type','current','read_at'],
        'properties':{'notification_id':{'type':'string'},'environment_id':{'type':'string'},'region':{'type':'string'},
            'type':{'type':'string','enum':['EXPIRY_SOON','RENEWAL_SUCCEEDED','RENEWAL_BLOCKED','RENEWAL_SYNC_PENDING','CONTINUOUS_BUDGET_WARNING','CONTINUOUS_COST_UNAVAILABLE','MAINTENANCE_NOTICE']},
            'current':{'type':'boolean','description':'False for superseded/elapsed deadline notices; kept in history.'},
            'read_at':nullable_time,'created_at':{'type':'integer'},'deadline':nullable_time,
            'remaining_seconds':{'type':'integer','minimum':0},'mode':{'type':'string'},'ending_policy':{'type':'string'},
            'period_estimate_milliusd':{'type':'integer','nullable':True},'cumulative_milliusd':{'type':'integer','nullable':True},
            'operation_id':{'type':'string'},'code':{'type':'string'},'email_status':{'type':'string',
                'description':'PUBLISHED means SNS accepted publish, not confirmed inbox delivery. UNKNOWN is never auto resent.'}}}
    schemas['NotificationList']={'type':'object','required':['items','warning_minutes','history','unread_count'],
        'properties':{'items':{'type':'array','items':ref('Notification')},'history':{'type':'array','items':ref('Notification')},
            'warning_minutes':{'type':'integer','enum':[15]},'unread_count':{'type':'integer','minimum':0},
            'truncated':{'type':'boolean'},'total_count':{'type':'integer'}}}
    schemas['NotificationPreferencesInput']={'type':'object','additionalProperties':False,
        'required':['email_enabled','expiry_email','renewal_email'],
        'properties':{key:{'type':'boolean'} for key in ['email_enabled','expiry_email','renewal_email','maintenance_email']}}
    schemas['NotificationPreferences']={'type':'object','required':['email_enabled','expiry_email','renewal_email','email_status','email_available','delivery_verified'],
        'properties':{**schemas['NotificationPreferencesInput']['properties'],'email_status':{'type':'string'},
            'email_available':{'type':'boolean'},'masked_email':{'type':'string','nullable':True},
            'updated_at':nullable_time,'delivery_verified':{'type':'boolean','enum':[False]}}}
    base=doc['paths']['/notifications']['get'];base['parameters']=[{'name':'schema','in':'query','schema':{'type':'string','enum':['2']},
        'description':'Use 2 for renewal outcomes/history. Omit to retain the legacy notification type subset.'}]
    for path,method,opid,result,body in [('/notifications/{notification_id}/read','post','markOwnedNotificationRead','Notification','Empty'),
        ('/account/notification-preferences','get','getNotificationPreferences','NotificationPreferences',None),
        ('/account/notification-preferences','post','setNotificationPreferences','NotificationPreferences','NotificationPreferencesInput'),
        ('/account/notification-preferences/check','post','checkNotificationEmailSubscription','NotificationPreferences','Empty')]:
        op={'operationId':opid,'security':base['security'],'responses':{code:{'description':description,'content':{'application/json':{'schema':ref(result if code=='200' else 'Error')}}}
            for code,description in [('200','OK'),('400','Invalid input'),('401','Authentication required'),('403','Verified enabled owner required'),('404','Owned notification not found'),('409','Setup busy or address changed'),('503','Email feature not enabled')]}}
        if '{notification_id}' in path:op['parameters']=[{'name':'notification_id','in':'path','required':True,'schema':{'type':'string','pattern':'^[a-z0-9-]{1,160}$'}}]
        if body:op['requestBody']={'required':True,'content':{'application/json':{'schema':ref(body)}}}
        if method=='post':op['description']='Owner-bound and idempotent for identical desired state. Does not renew or mutate an environment. Email opt-in can send one SNS confirmation to the server-verified address; no client endpoint/owner accepted.'
        doc['paths'].setdefault(path,{})[method]=op
