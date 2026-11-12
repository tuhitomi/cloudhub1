"""UI product endpoints. Admin claims are revalidated against live Cognito."""
from .runtime import driver_settings
import json,os,re
from .errors import HubError

UNHANDLED=object()

def route(service, method, path, body, key, owner, admin, claims, query, public, identity=None):
    accounts=None
    if path.startswith('/admin/') or method=='POST' and path=='/environments' and body.get('validation_run') is True:
        if not admin:raise HubError('FORBIDDEN','Cần quyền quản trị.',403)
        from .accounts import Accounts
        accounts=Accounts(os.environ['USER_POOL_ID'])
        accounts.assert_admin(owner,claims.get('username'))
    if path.startswith('/admin/announcements'):
        from .announcements import Announcements
        center=Announcements(service,os.getenv('MAINTENANCE_PUBLIC_ENABLED','false').lower()=='true')
        if path=='/admin/announcements':
            if method=='GET':return center.listing(),200
            if method=='POST':return center.create(owner,key,body),201
        match=re.fullmatch(r'/admin/announcements/(ann-[a-f0-9]{24})(?:/(preview|publish|cancel|retry))?',path)
        if match:
            aid,action=match.groups()
            if method=='GET' and action is None:return center.view(center.get(aid)),200
            if method=='PUT' and action is None:return center.edit(owner,aid,key,body),200
            if method=='POST' and action=='preview':return center.preview(owner,aid,body),200
            if method=='POST' and action in {'publish','cancel','retry'}:
                value=getattr(center,'retry_sync' if action=='retry' else action)(owner,aid,key,body)
                return value,202
        raise HubError('NOT_FOUND','Announcement route not found.',404)
    if method=='GET' and path=='/limits':return service.limits(owner),200
    if path=='/admin/spend-guard':
        from . import spend_guard
        if method=='GET':return spend_guard.view(service),200
        if method=='POST':return spend_guard.set_state(service,owner,body,int(service.clock())),200
    if path=='/admin/signup-defaults':
        from .registration import defaults, set_defaults
        if method=='GET':return defaults(service),200
        if method=='POST':return set_defaults(service,owner,body),200
    if method=='GET' and path=='/notifications':
        result=service.notifications(owner)
        if query.get('schema')!='2':
            # Old cached clients assume every unknown type means renewal failure.
            result={**result,'items':[dict(item,message_key={'EXPIRY_SOON':'notice.expirySoon',
                'RENEWAL_BLOCKED':'notice.renewalBlocked','CONTINUOUS_BUDGET_WARNING':'continuous.budgetWarning',
                'CONTINUOUS_COST_UNAVAILABLE':'continuous.pricesUnavailable'}[item['type']])
                for item in result['items'] if item['type'] in {'EXPIRY_SOON','RENEWAL_BLOCKED','CONTINUOUS_BUDGET_WARNING','CONTINUOUS_COST_UNAVAILABLE'}]}
        return result,200
    if path=='/account/notification-preferences' or path=='/account/notification-preferences/check':
        from .notifications import NotificationCenter
        from .notification_email import runtime_gateway
        center=NotificationCenter(service);gateway=runtime_gateway()
        if path.endswith('/check') and method=='POST':
            if body:raise HubError('INVALID_INPUT','Expected empty input.')
            return center.preferences_check(owner,gateway,identity),200
        if path=='/account/notification-preferences' and method=='GET':return center.preferences(owner,gateway is not None),200
        if path=='/account/notification-preferences' and method=='POST':return center.preferences_update(owner,body,gateway,identity),200
    if method=='POST' and re.fullmatch(r'/notifications/[a-z0-9-]{1,160}/read',path):
        if body:raise HubError('INVALID_INPUT','Expected empty input.')
        from .notifications import NotificationCenter
        return NotificationCenter(service).read(owner,path.split('/')[2]),200
    if method=='GET' and path=='/operations':
        return {'items':[public(o) for o in sorted(service.store.list_owner(owner,'operation'),key=lambda o:o.get('created_at',0),reverse=True)[:100]]},200
    if method=='GET' and re.fullmatch(r'/environments/[a-z0-9-]+/renewals',path):
        history=service.renewal_history(owner,path.split('/')[2]);history['items']=[public(row) for row in history['items']]
        return history,200
    if method=='POST' and re.fullmatch(r'/environments/[a-z0-9-]+/management-estimate',path):
        return service.management_estimate(owner,path.split('/')[2],body),200
    if method=='POST' and re.fullmatch(r'/environments/[a-z0-9-]+/(renew|change_policy|resume_paused|end)',path):
        _,eid,action=path.strip('/').split('/')
        return public(getattr(service,action)(owner,eid,key,body)),202
    if method=='POST' and re.fullmatch(r'/operations/[a-z0-9-]+/(retry|cancel)',path):
        _,oid,action=path.strip('/').split('/')
        return public(service.control_operation(owner,oid,action,key,body)),202 if action=='retry' else 200
    if method=='POST' and re.fullmatch(r'/recovery-points/[a-z0-9-]+/(delete|export)',path):
        _,rid,action=path.strip('/').split('/')
        return public(service.backup_command(owner,rid,'delete_backup' if action=='delete' else 'export_backup',key,body)),202
    if method=='GET' and re.fullmatch(r'/operations/[a-z0-9-]+/download',path):
        from .backup_export import download
        return download(service,owner,path.split('/')[2],driver_settings()),200
    if re.fullmatch(r'/environments/[a-z0-9-]+/cost',path):
        eid=path.split('/')[2]
        if method=='GET':return service.owned('E',eid,owner).get('cost_report',{'status':'NOT_REQUESTED','actual_milliusd':None}),200
        if method=='POST':return public(service.cost_command(owner,eid,key,body)),202
    if method=='GET' and path=='/admin/environments':
        from .test_visibility import environments
        from .admin_directory import environment_owners
        result=environments(service.store.scan_kind('environment'),query,public)
        return environment_owners(result,accounts,int(service.clock())),200
    if method=='GET' and re.fullmatch(r'/admin/operations/[a-z0-9-]+',path):
        row=service.store.get('O#'+path.split('/')[-1])
        if not row:raise HubError('NOT_FOUND','Không tìm thấy tác vụ.',404)
        return public(row),200
    if method=='GET' and path=='/admin/users':
        from .admin_directory import users
        return users(service,accounts,query),200
    if method=='POST' and path=='/admin/users':
        result=accounts.create_idempotent(service,owner,key,body)
        return result,201 if result['invitation_status']=='CREATED' else 200
    match=re.fullmatch(r'/admin/users/([a-f0-9-]{36})/(limits|enabled)',path)
    if method=='POST' and match:
        target,action=match.groups();accounts.find(target)
        if action=='limits':return service.set_limits(owner,target,body),200
        if set(body)!={'enabled'}:raise HubError('INVALID_INPUT','Cần trường enabled.')
        return accounts.set_enabled(owner,target,body['enabled'],service),200
    if method=='POST' and re.fullmatch(r'/admin/environments/[a-z0-9-]+/retire',path):
        if set(body)!={'reason'} or not isinstance(body['reason'],str) or not 10<=len(body['reason'].strip())<=500:
            raise HubError('INVALID_INPUT','Cần lý do thu hồi từ 10 đến 500 ký tự.')
        env=service.store.get('E#'+path.split('/')[3])
        if not env:raise HubError('NOT_FOUND','Không tìm thấy môi trường.',404)
        return public(service.command(env['owner_id'],env['environment_id'],'destroy',key,admin_actor=owner,reason=body['reason'])),202
    if method=='GET' and path=='/admin/notifications':
        from .accounts import subscription_status
        return subscription_status(os.getenv('ALERT_TOPIC_ARN'),os.getenv('ALERT_EMAIL')),200
    if method=='POST' and path=='/admin/notifications/test':
        if body!={'confirm_send':True}:raise HubError('INVALID_INPUT','Cần xác nhận gửi email kiểm tra.')
        from .accounts import subscription_status
        topic=os.getenv('ALERT_TOPIC_ARN');state=subscription_status(topic,os.getenv('ALERT_EMAIL'))
        if state['status']!='CONFIRMED':raise HubError('SNS_UNCONFIRMED','Người nhận chưa xác nhận đăng ký SNS.',409)
        import boto3
        result=boto3.client('sns').publish(TopicArn=topic,Subject='CloudHub - Kiem tra canh bao',Message='CloudHub: email kiểm tra cảnh báo vận hành. Hãy xác nhận đã nhận thư trong minh chứng triển khai.')
        return {'status':'PUBLISHED','message_id':result['MessageId'],'delivery_verified':False},200
    return UNHANDLED
