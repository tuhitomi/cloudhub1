"""HTTP API v2 Lambda adapter; trust only API Gateway validated JWT claims."""
import base64
import json
import logging
import os
from .runtime import driver_settings
import re
import time
from decimal import Decimal
from .catalog import catalog
from .catalog import ACTIVE_TEMPLATES
from .errors import HubError

log = logging.getLogger(__name__)
SERVICE = None
DISPATCH = None

def serialize(value):
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral() else str(value)
    raise TypeError(type(value).__name__)

def public(row):
    result={k: v for k, v in row.items() if k not in {"pk", "version", "owner_sort", "restore_lock", "retirement_lock", "file",'data','warehouse_secret'}}
    if row.get('kind')=='recovery':
        result['in_use']=bool(row.get('restore_lock') or row.get('export_lock') or row.get('delete_lock'))
        result['retirement_protected']=bool(row.get('retirement_lock'))
        if SERVICE:
            from .recovery_actions import availability
            result['action_availability']=availability(SERVICE,row)
    if SERVICE and row.get('kind') in {'environment','recovery','operation'} and not result.get('region'):
        try:result['region']=SERVICE.region_for(row)
        except HubError:result['region_status']='VERIFICATION_REQUIRED'
    if result.get('error'):
        code=str(result['error']).split(':',1)[0]
        if not re.fullmatch('[A-Z][A-Z0-9_]{2,80}',code):code='OPERATION_FAILED'
        result['error']=code+'; support: '+str(row.get('operation_id',row.get('environment_id','')))
    if SERVICE and row.get('kind')=='environment':
        result['continuous_available']=SERVICE.continuous_available(row)
        if row.get('application'):
            from .quotes import fingerprint
            result['application_etag']=fingerprint(row['application'])
    return result

def handler(event, context=None):
    global SERVICE, DISPATCH
    started=time.perf_counter();timings={}
    if event.get('rawPath')=='/ui-context' and event.get('requestContext',{}).get('http',{}).get('method')=='GET':
        from .ui_context import context as ui_context
        return response(200,ui_context(event,os.environ.get('UI_EDGE_SECRET')))
    if SERVICE is None:
        from .runtime import build_service, dispatch, enqueue_dispatch
        SERVICE, DISPATCH = build_service(), enqueue_dispatch if os.getenv("ASYNC_DISPATCH_FUNCTION") else dispatch
    if event.get('rawPath')=='/public/catalog' and event.get('requestContext',{}).get('http',{}).get('method')=='GET':
        from .public_catalog import read as public_catalog
        try:return response(200,public_catalog(SERVICE,event.get('queryStringParameters')))
        except HubError as exc:return response(exc.status,{'error':{'code':exc.code,'message':exc.message}})
        except Exception:
            log.exception('Public catalog unavailable')
            return response(503,{'error':{'code':'PUBLIC_CATALOG_UNAVAILABLE','message':'Public preview is temporarily unavailable.'}})
    rid = event.get("requestContext", {}).get("requestId", "local")
    try:
        claims = event.get("requestContext", {}).get("authorizer", {}).get("jwt", {}).get("claims", {})
        owner = claims.get("sub")
        if not owner or claims.get("token_use") != "access":
            raise HubError("UNAUTHORIZED", "Cần access token Cognito hợp lệ.", 401)
        groups = claims.get("cognito:groups", "")
        if isinstance(groups, str):
            groups = re.findall(r"[A-Za-z0-9_-]+", groups)
        admin = "admin" in groups
        account = SERVICE.store.get('U#'+owner)
        if account and account.get('enabled') is False:
            raise HubError('ACCOUNT_DISABLED','Tài khoản đã bị khóa.',403)
        method = event["requestContext"]["http"]["method"]
        path = event.get("rawPath", "/")
        from .accounts import Accounts
        from .registration import ensure_profile
        identity = Accounts(os.environ['USER_POOL_ID']).identity(owner, claims.get('username'))
        if not identity['email_verified'] and not (method == 'GET' and path == '/account'):
            raise HubError('EMAIL_NOT_VERIFIED', 'Xác thực email trước khi quản lý môi trường.', 403)
        profile = ensure_profile(SERVICE, identity) if identity['email_verified'] else {
            'owner_id': owner, 'email': identity['email'], 'email_verified': False, 'role': 'user'}
        timings["identity_ms"]=round((time.perf_counter()-started)*1000,2)
        # Warm API containers must observe admission/proof changes within the
        # existing 60-second runtime cache, even without a prior catalog request.
        SERVICE.refresh_region_policy()
        headers = {k.lower(): v for k, v in event.get("headers", {}).items()}
        raw = event.get("body") or "{}"
        if event.get("isBase64Encoded"):
            raw = base64.b64decode(raw).decode()
        if len(raw) > 16384:
            raise HubError("INVALID_INPUT", "Yêu cầu quá lớn.", 413)
        body = json.loads(raw)
        if not isinstance(body, dict):
            raise HubError("INVALID_INPUT", "Nội dung phải là JSON object.")
        key = headers.get("idempotency-key")
        status = 200
        from .portal_api import route, UNHANDLED
        extra = route(SERVICE,method,path,body,key,owner,admin,claims,event.get('queryStringParameters') or {},public,identity)
        if method == 'GET' and path == '/account':
            result = profile
        elif method=='PUT' and path=='/account/preferences':
            from .ui_context import preference
            result=preference(SERVICE,owner,body,event.get('requestContext',{}).get('timeEpoch'))
        elif extra is not UNHANDLED:
            result,status=extra
        elif method == "GET" and path == "/templates":
            SERVICE.refresh_pricing(cached=True)
            result = {"items": catalog(SERVICE.verified,SERVICE.estimator.rates.get('configuration_verifications',{}))}
            for item in result['items']:
                if item['template_id'] in {'T03','T04'}:
                    from .applications import options as application_options
                    item['application_options']={r:application_options(SERVICE,item['template_id'],r) for r in ['ap-southeast-1','ap-northeast-1','us-east-1']}
                item['default_region']=SERVICE.region_registry().home
                item['regions']=SERVICE.region_options(item['template_id'])
                for r in item['regions']:
                    for p in r['configuration_options']:
                        p['operating_modes']=['AUTO_OFF','AUTO_RENEW']+(['CONTINUOUS'] if SERVICE.continuous_available({'template_id':item['template_id'],'region':r['region'],'configuration':p['configuration']}) else [])
                    r['operating_modes']=['AUTO_OFF','AUTO_RENEW']+(['CONTINUOUS'] if any('CONTINUOUS' in p['operating_modes'] for p in r['configuration_options']) else [])
                if any('CONTINUOUS' in r['operating_modes'] for r in item['regions']):item['operating_capabilities']['modes'].append('CONTINUOUS')
                item['create_enabled']=any(p['create_enabled'] for r in item['regions'] for p in r['configuration_options'])
        elif method=='GET' and path=='/regions':
            SERVICE.refresh_pricing(cached=True)
            registry=SERVICE.region_registry()
            from .regions import REGIONS
            result={'default_region':registry.home,'items':[{'region':r,'name':name,'templates':{tid:next(x for x in SERVICE.region_options(tid) if x['region']==r) for tid in sorted(ACTIVE_TEMPLATES)}} for r,name in REGIONS.items()]}
        elif method=='GET' and path=='/recommendations/schema':
            if not SERVICE.recommendations_enabled:raise HubError('RECOMMENDATIONS_DISABLED','Configuration advice is not enabled yet.',503)
            from .recommendations import schema as recommendation_schema
            result=recommendation_schema(SERVICE)
        elif method=='POST' and path=='/recommendations':
            if not SERVICE.recommendations_enabled:raise HubError('RECOMMENDATIONS_DISABLED','Configuration advice is not enabled yet.',503)
            from .recommendations import recommend
            result=recommend(SERVICE,owner,body)
        elif method=='POST' and re.fullmatch(r'/environments/[a-z0-9-]+/application',path):
            from .applications import begin as deploy_application
            result,status=public(deploy_application(SERVICE,owner,path.split('/')[2],key,body,admin)),202
        elif path.startswith('/admin/benchmarks'):
            from .benchmarks import admin_route
            result=admin_route(SERVICE,method,path,body,owner,admin)
            if result is None:raise HubError('NOT_FOUND','Unsupported benchmark route.',404)
        elif method == "POST" and path == "/estimates":
            result = SERVICE.create_estimate(owner, body, admin)
        elif method == "POST" and path == "/environments":
            result, status = public(SERVICE.create(owner, key, body, admin)), 202
        elif method=='GET' and re.fullmatch(r'/operations/[a-z0-9-]+/actions',path):
            result=SERVICE.operation_actions(owner,path.split('/')[2])
        elif method=='POST' and re.fullmatch(r'/environments/[a-z0-9-]+/files/metadata',path):
            from .s3_files import OwnedFiles
            result=OwnedFiles(SERVICE,driver_settings()).metadata(owner,path.split('/')[2],body)
        elif method=='POST' and re.fullmatch(r'/environments/[a-z0-9-]+/releases',path):
            from .releases import begin
            result=begin(SERVICE,owner,path.split('/')[2],key,body)
        elif method=='POST' and re.fullmatch(r'/environments/[a-z0-9-]+/releases/activate',path):
            from .releases import activate
            result,status=public(activate(SERVICE,owner,path.split('/')[2],key,body)),202
        elif method=='POST' and re.fullmatch(r'/environments/[a-z0-9-]+/uploads',path):
            from .uploads import Uploads
            result=Uploads(SERVICE,driver_settings()).initiate(owner,path.split('/')[2],key,body)
        elif method=='POST' and re.fullmatch(r'/environments/[a-z0-9-]+/uploads/upload-[a-f0-9]+/cancel',path):
            from .uploads import Uploads
            result=Uploads(SERVICE,driver_settings()).cancel(owner,path.split('/')[2],path.split('/')[4],key,body)
        elif method=='POST' and re.fullmatch(r'/environments/[a-z0-9-]+/uploads/upload-[a-f0-9]+/complete',path):
            from .uploads import Uploads
            result,status=public(Uploads(SERVICE,driver_settings()).complete(owner,path.split('/')[2],path.split('/')[4],key,body)),202
        elif method == "GET" and path in {"/environments", "/recovery-points"}:
            kind = "environment" if path == "/environments" else "recovery"
            rows=SERVICE.store.list_owner(owner,kind)
            if kind=='environment':
                from .test_visibility import environments
                result=environments(rows,event.get('queryStringParameters') or {},public)
            else:result={"items":[public(r) for r in rows]}
        elif method == "GET" and path == "/admin/attention":
            if not admin:
                raise HubError("FORBIDDEN", "Cần quyền quản trị.", 403)
            result = {"items": [public(r) for r in SERVICE.store.scan_kind("environment") if r.get("needs_admin") or r["status"] == "RESIDUAL"]}
        elif method == "GET" and re.fullmatch(r"/environments/[a-z0-9-]+/ssh-key", path):
            from .access import ssh_key
            result = ssh_key(SERVICE, owner, path.strip("/").split("/")[1])
        elif method == 'GET' and re.fullmatch(r'/environments/env-[a-f0-9]{24}/template',path):
            if event.get('queryStringParameters'):
                raise HubError('INVALID_INPUT','Template view does not accept stack, Region or format overrides.')
            from .template_view import read as read_template
            result=read_template(SERVICE,owner,path.split('/')[2])
        elif method in {"GET", "POST"} and re.fullmatch(r"/environments/[a-z0-9-]+/files", path):
            eid = path.strip("/").split("/")[1]
            if method == "POST":
                result, status = public(SERVICE.write_file(owner, eid, key, body)), 202
            else:
                from .s3_files import OwnedFiles
                result = OwnedFiles(SERVICE, driver_settings()).list(owner, eid)
        elif method == "GET" and re.fullmatch(r"/(environments|operations|recovery-points)/[a-z0-9-]+", path):
            group, entity_id = path.strip("/").split("/")
            kind = {"environments": "E", "operations": "O", "recovery-points": "R"}[group]
            result = public(SERVICE.environment_detail(owner,entity_id) if kind=="E" else SERVICE.owned(kind, entity_id, owner))
        elif method=='POST' and re.fullmatch(r'/environments/[a-z0-9-]+/share',path):
            from .s3_files import OwnedFiles
            result=OwnedFiles(SERVICE,driver_settings()).share(owner,path.strip('/').split('/')[1],body)
        elif method=='POST' and re.fullmatch(r'/environments/[a-z0-9-]+/(put_record|list_records|load_dataset|query_demo)',path):
            _,eid,action=path.strip('/').split('/')
            result,status=public(SERVICE.data_command(owner,eid,action,key,body)),202
        elif method == "POST" and re.fullmatch(r"/environments/[a-z0-9-]+/(backup|destroy|audit|extend)", path):
            _, eid, action = path.strip("/").split("/")
            if action == "extend":
                result,status = public(SERVICE.extend(owner, eid, key, body)),202
            else:
                result, status = public(SERVICE.command(owner, eid, action, key, body)), 202
        else:
            raise HubError("NOT_FOUND", "Đường dẫn không tồn tại.", 404)
        timings["validated_and_committed_ms"]=round((time.perf_counter()-started)*1000,2)
        if status == 202 and DISPATCH:
            try:
                DISPATCH(result["operation_id"])
            except Exception:
                # Durable outbox: sweeper retries dispatch, same execution name/input.
                log.exception("Dispatch deferred for %s", result["operation_id"])
        if status==202:
            print(json.dumps({"event":"CloudHubAcceptanceTimings","request_id":rid,**timings,"total_ms":round((time.perf_counter()-started)*1000,2)}))
        return response(status, result)
    except (ValueError, UnicodeError, KeyError, TypeError):
        return response(400, {"error": {"code": "INVALID_INPUT", "message": "Yêu cầu không hợp lệ.", "request_id": rid}})
    except HubError as exc:
        if exc.code in {'PRICES_UNAPPROVED','CONFIGURATION_UNVERIFIED','REGION_UNAVAILABLE'}:exc.details['review_required']=True
        return response(exc.status, {"error": {"code": exc.code, "message": exc.message, "request_id": rid, **exc.details}})
    except Exception:
        log.exception("Internal error request=%s", rid)
        return response(500, {"error": {"code": "INTERNAL_ERROR", "message": "Lỗi xử lý; giữ nguyên Idempotency-Key khi thử lại.", "request_id": rid}})

def response(status, body):
    return {"statusCode": status, "headers": {"content-type": "application/json; charset=utf-8", "cache-control": "no-store"},
            "body": json.dumps(body, ensure_ascii=False, default=serialize)}
