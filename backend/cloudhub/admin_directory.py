"""Admin-only directory presentation. Email is never used as ownership authority."""
import re
from botocore.exceptions import ClientError,BotoCoreError
from .errors import HubError
from .test_visibility import include_tests,hidden_account

def search_term(query):
    value=query.get('q','')
    if not isinstance(value,str) or len(value)>128 or any(ord(c)<32 for c in value):
        raise HubError('INVALID_INPUT','Search must be at most 128 characters.')
    return value.strip()

def users(service,accounts,query):
    include=include_tests(query);term=search_term(query);needle=term.casefold()
    cursor=query.get('cursor');visible=[];hidden=0;pages=0
    # Bounded continuation supports substring search across pages without an
    # unbounded Lambda scan. A returned cursor means search is not exhaustive.
    for _ in range(3 if needle else 1):
        page=accounts.list(cursor);pages+=1
        for raw in page['items']:
            user=dict(raw);owner=user.get('owner_id');local=service.store.get('U#'+owner) if owner else None
            if local and local.get('test_data'):user['test_data']=local['test_data']
            if not include and hidden_account(user,local):hidden+=1;continue
            if needle and needle not in ' '.join(str(user.get(k,'')) for k in ['email','username','owner_id']).casefold():continue
            if owner:
                user['limits']=service.limits(owner);user['cognito_enabled']=user['enabled']
                if local and local.get('enabled') is False:user['enabled']=False
            visible.append(user)
        cursor=page.get('next_cursor')
        if not cursor:break
    return {'items':visible,'next_cursor':cursor,'hidden_test_count':hidden,'test_data_included':include,
        'search_query':term,'search_complete':not bool(cursor),'directory_pages_scanned':pages}

def environment_owners(result,accounts,checked_at):
    items=[dict(row) for row in result['items']]
    targets={row['owner_id'] for row in items if re.fullmatch(r'[a-f0-9-]{36}',str(row.get('owner_id','')))}
    missing=set(targets);emails={};cursor=None;unavailable=False
    try:
        for _ in range(5 if targets else 0):
            page=accounts.list(cursor)
            for user in page['items']:
                owner=user.get('owner_id');address=user.get('email')
                if owner in missing and isinstance(address,str) and '@' in address and len(address)<=254:
                    emails[owner]=address;missing.remove(owner)
            cursor=page.get('next_cursor')
            if not cursor or not missing:break
    except (ClientError,BotoCoreError):unavailable=True
    for row in items:
        owner=row.get('owner_id');row['owner_email']=emails.get(owner)
        row['owner_email_status']=('FOUND' if owner in emails else 'LEGACY_ID' if owner not in targets else
            'UNAVAILABLE' if unavailable else 'UNRESOLVED' if cursor else 'NOT_FOUND')
    return {**result,'items':items,'owner_directory_checked_at':checked_at}
