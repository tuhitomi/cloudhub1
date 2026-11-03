"""Preview/apply reversible test presentation metadata; no AWS I/O on import."""
import hashlib
from copy import deepcopy

def synthetic(user):
    mail=str(user.get('email','')).lower()
    return user.get('enabled') is False and mail.startswith(('cloudhub-','cloudhub08-')) and mail.endswith('@example.invalid')

def plan(rows,users):
    from cloudhub.test_visibility import hidden_environment
    owners={u['owner_id'] for u in users if synthetic(u)}
    marker={'schema':1,'classification':'TEST','hidden_by_default':True}
    items=[{'pk':'U#'+u['owner_id'],'owner_id':u['owner_id'],'kind':'account','evidence':'DISABLED_RESERVED_SYNTHETIC_COGNITO'} for u in users if synthetic(u)]
    for row in rows:
        if row.get('kind')!='environment':continue
        if row.get('validation_run') is not True and row.get('owner_id') not in owners:continue
        if not hidden_environment({**row,'test_data':marker}):continue
        items.append({'pk':row['pk'],'owner_id':row['owner_id'],'kind':'environment',
            'evidence':'SERVER_ADMIN_VALIDATION_RUN' if row.get('validation_run') is True else 'DISABLED_RESERVED_SYNTHETIC_OWNER'})
    return {'schema':1,'items':sorted(items,key=lambda v:v['pk']),
        'effect':'Presentation only. Preserve financial history, backups, operations, AWS resources and all human accounts.'}

def commit_legacy_profile(store,changed,audit,before):
    """Fence an existing pre-version U# row without replacing unknown fields."""
    from cloudhub.store import DynamoStore
    from cloudhub.errors import Conflict
    from cloudhub.service import expected
    if not isinstance(store,DynamoStore):
        # MemoryStore's locked compare permits existing rows without versions.
        store.commit([changed,audit],expected(changed,audit));return
    from botocore.exceptions import ClientError
    names={'#version':'version'};values={};conditions=['attribute_exists(pk)','attribute_not_exists(#version)']
    for index,(key,value) in enumerate(before.items()):
        if key=='pk':continue
        nk='#old'+str(index);vk=':old'+str(index);names[nk]=key;values[vk]=store.ser.serialize(value);conditions.append(nk+' = '+vk)
    setters=[]
    for index,key in enumerate(['test_data','owner_id','enabled','version']):
        nk='#set'+str(index);vk=':set'+str(index);names[nk]=key
        values[vk]=store.ser.serialize(1 if key=='version' else changed[key]);setters.append(nk+' = '+vk)
    row=dict(audit,version=1)
    try:
        store.client.transact_write_items(TransactItems=[{'Update':{'TableName':store.table,'Key':store.encode({'pk':before['pk']}),
            'UpdateExpression':'SET '+', '.join(setters),'ConditionExpression':' AND '.join(conditions),
            'ExpressionAttributeNames':names,'ExpressionAttributeValues':values}},
            {'Put':{'TableName':store.table,'Item':store.encode(row),'ConditionExpression':'attribute_not_exists(pk)'}}])
    except ClientError as exc:
        if exc.response['Error']['Code'] in {'TransactionCanceledException','TransactionConflictException'}:raise Conflict() from exc
        raise

def archive(store,item,now,accounts=None):
    from cloudhub.service import retry,expected
    from cloudhub.test_visibility import marked,hidden_environment
    kind=item.get('kind');prefix='E#' if kind=='environment' else 'U#' if kind=='account' else None
    if not prefix or not item.get('pk','').startswith(prefix):raise ValueError('Only reviewed E#/U# test records may be archived')
    if kind=='account' and item['pk']!='U#'+item.get('owner_id',''):raise ValueError('Account key must match the verified Cognito subject')
    if item.get('evidence') not in {'SERVER_ADMIN_VALIDATION_RUN','DISABLED_RESERVED_SYNTHETIC_OWNER','DISABLED_RESERVED_SYNTHETIC_COGNITO'}:raise ValueError('Reviewed test provenance required')
    if kind=='account' and accounts is None:raise ValueError('Live Cognito verification is mandatory for accounts')
    def commit():
        if kind=='account':
            identity=accounts.find(item['owner_id'])
            if identity.get('owner_id')!=item['owner_id'] or not synthetic(identity):return 'PROVIDER_STATE_CHANGED_REVIEW_REQUIRED'
        row=store.get(item['pk'])
        if row is None:
            if kind!='account':return 'MISSING_REVIEW_REQUIRED'
            row={'pk':item['pk'],'kind':'account','owner_id':item['owner_id'],'enabled':False}
        owner=row.get('owner_id')
        if owner!=item['owner_id'] and not (kind=='account' and owner is None):return 'OWNER_CHANGED_REVIEW_REQUIRED'
        if marked(row):return 'ALREADY_ARCHIVED'
        changed=deepcopy(row)
        changed['test_data']={'schema':1,'classification':'TEST','hidden_by_default':True,'archived_at':now,'evidence':item['evidence']}
        if kind=='environment' and not hidden_environment(changed):return 'STATE_CHANGED_REVIEW_REQUIRED'
        if kind=='account':
            # Cognito was verified disabled in this attempt. Sync only a stale
            # local flag; never call enable/disable or change provider access.
            changed['enabled']=False
            # Legacy cleanup wrote some U# rows without owner_id. The exact
            # subject key and fresh Cognito lookup above are both required.
            if owner is None:changed['owner_id']=item['owner_id']
        audit={'pk':'M#test-visibility-'+hashlib.sha256(item['pk'].encode()).hexdigest()[:24],
            'kind':'test_visibility_audit','target_pk':item['pk'],'owner_id':item['owner_id'],
            'created_at':now,'evidence':item['evidence'],'action':'HIDE_FROM_DEFAULT_LIST','data_deleted':False,
            'previous_test_data':row.get('test_data'),'previous_profile_enabled':row.get('enabled'),'previous_owner_id':owner,
            'previous_profile_existed':store.get(item['pk']) is not None}
        if store.get(audit['pk']) is not None:return 'PRIOR_AUDIT_REVIEW_REQUIRED'
        if kind=='account' and 'version' not in row and store.get(item['pk']) is not None:
            commit_legacy_profile(store,changed,audit,row)
        else:store.commit([changed,audit],expected(changed,audit))
        return 'ARCHIVED'
    return retry(commit)
