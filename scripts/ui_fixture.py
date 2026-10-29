"""Loopback-only UI fixtures. Synthetic session/prices/resources; NEVER an AWS client.

Run python scripts/ui_fixture.py, visit http://127.0.0.1:8765/?scenario=empty.
Scenarios: empty, loading, error, submit-error, uncertain, long, quota, guest, ready, paused, admin.
All outgoing connections blocked by CSP. Only explicit public source assets served.
"""
import argparse
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import time
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
from cloudhub.catalog import catalog,configuration,configuration_profiles,configuration_key,ACTIVE_TEMPLATES

from public_assets import ASSETS as PUBLIC_ASSETS
ASSETS=set(PUBLIC_ASSETS)
FIXTURE_COUNTRY=None

SCENARIOS = {'empty', 'loading', 'error', 'submit-error', 'uncertain', 'long', 'quota', 'guest', 'ready', 'paused', 'admin','unverified-config','files','records','studio','unverified-user','notifications','wallet-platform'}
STATE = {}
LOCK = threading.Lock()
from cloudhub.service import Service
from cloudhub.store import MemoryStore
from cloudhub.announcements import Announcements
MAINTENANCE_SERVICE=Service(MemoryStore())
MAINTENANCE=Announcements(MAINTENANCE_SERVICE)
MAINTENANCE_PUBLIC={'schema':1,'publisher':'cloudhub-maintenance','generation':0,'active':False,'announcement':None}
class LocalNoticeWriter:
    def token(self):return 'local-fixture-token'
    def write(self,payload,current):
        global MAINTENANCE_PUBLIC
        if current():MAINTENANCE_PUBLIC=payload;return {'sha256':'LOCAL_FIXTURE_NOT_AWS'}


def scenario_state(name):
    with LOCK:
        if name not in STATE:
            envs=[]
            if name in {'ready','paused','admin','files','records','studio','notifications'}:
                envs=[{'environment_id':'env-local-existing','template_id':'T05','status':'PAUSED' if name=='paused' else 'READY','owner_id':'local-only','region':'ap-southeast-1',
                       'operating_policy':{'mode':'AUTO_OFF','period_minutes':60,'ending_policy':'PAUSE','budget_limit_milliusd':None,'confirmed':True},'lifecycle_revision':3,
                       'estimated_committed_milliusd':454,'first_period_estimate':{'total_milliusd':350},'estimate_hours':4,'deadline':int(time.time())+3600,
                       'pause_report':{'deleted':[],'retained':[{'id':'vol-local','type':'AWS::EC2::Volume'}],'residual':[],'unknown':[],
                                       'billable':[{'id':'vol-local','type':'AWS::EC2::Volume'}],'cost_note':'GIẢ LẬP: máy dừng, EBS còn phí.'}}]
                if name in {'files','records','studio'}:
                    envs[0].update(template_id='T07' if name=='files' else 'T02' if name=='studio' else 'T09',
                                   operating_policy={'mode':'AUTO_OFF','period_minutes':60,'ending_policy':'BACKUP_RETIRE','confirmed':True})
            STATE[name] = {'estimate_calls': 0, 'create_calls': 0, 'ops': {}, 'keys': {}, 'envs': envs}
            if name=='notifications':
                stamp=int(time.time());envs[0]['deadline']=stamp+600
                common={'environment_id':'env-local-existing','template_id':'T05','region':'ap-southeast-1',
                        'created_at':stamp,'deadline':stamp+600,'lifecycle_revision':3,'ending_policy':'PAUSE',
                        'currency':'USD','mode':'AUTO_OFF','read_at':None,'current':True,'email_status':'NOT_REQUESTED'}
                STATE[name]['notices']=[dict(common,notification_id='notice-local-expiry',type='EXPIRY_SOON'),
                    dict(common,notification_id='notice-local-renewal',type='RENEWAL_SUCCEEDED',operation_id='op-local-renewal',period_estimate_milliusd=350,cumulative_milliusd=804),
                    dict(common,notification_id='notice-local-history',type='EXPIRY_SOON',current=False,deadline=stamp-3600)]
                STATE[name]['notification_preferences']={'email_available':True,'email_enabled':False,'expiry_email':True,
                    'renewal_email':True,'email_status':'DISABLED','masked_email':None,'delivery_verified':False}
        return STATE[name]


def make_quote(body):
    expanded=bool(body.get('configuration') and body['configuration']!=configuration(body['template_id']))
    money = {'approved': True, 'total_milliusd': 350, 'region': body.get('region','ap-southeast-1'),
             'price_updated_at': 'Dữ liệu giả lập cục bộ, không phải đơn giá AWS',
             'units': {'fixture_unit': '0.010'}, 'assumptions': {'fixture': True}}
    return {**body, 'approved': True, 'currency': 'USD', 'preview': {**money, 'total_milliusd': 500},
            'first_period': {**money,'total_milliusd':550 if expanded else 350}, 'renewal_period': {**money, 'total_milliusd':300 if expanded else 200},
            'after_shutdown': {**money, 'total_milliusd': 104, 'period_hours': 24 if body['operating_policy']['ending_policy']=='PAUSE' else 168, 'unknown': []},
            'total_milliusd': 654 if expanded else 454, 'initial_commitment_milliusd': 654 if expanded else 454,'configuration_verified':True,
            'budget_feasible': body['operating_policy']['mode'] != 'AUTO_RENEW' or body['operating_policy']['budget_limit_milliusd'] >= 454,
            'budget_scope': 'GIẢ LẬP: cộng dồn kỳ đầu và mọi gia hạn, không đặt lại khi đổi chế độ.',
            'unknown': ['GIẢ LẬP: không phải số đo hay chi phí AWS; dùng để kiểm tra bố cục và tương tác.']}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Do not record headers/session data.

    def send(self, data, status=200, content_type='application/json; charset=utf-8'):
        payload = data.encode('utf-8') if isinstance(data, str) else json.dumps(data, ensure_ascii=False,default=str).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(payload)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; connect-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-src 'none'")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        parsed = urlsplit(self.path)
        if parsed.path=='/maintenance.json':return self.send(MAINTENANCE_PUBLIC)
        if parsed.path=='/ui-context':return self.send({'country_code':FIXTURE_COUNTRY,'source':'LOCAL_SIMULATED_COUNTRY','suggested_language':__import__('cloudhub.ui_context',fromlist=['locale_for_country']).locale_for_country(FIXTURE_COUNTRY)})
        if parsed.path.startswith('/api/'):
            return self.api('GET', parsed.path)
        name = parse_qs(parsed.query).get('scenario', ['empty'])[0]
        if name not in SCENARIOS:
            return self.send({'error': 'Unknown fixture scenario'}, 400)
        if parsed.path == '/config.js':
            return self.send("window.CLOUDHUB=Object.freeze({configured:true,apiBase:location.origin+'/api/'+(new URLSearchParams(location.search).get('scenario')||'empty'),clientId:'localfixture',cognitoDomain:location.origin,redirectUri:location.origin,region:'ap-southeast-1'});", content_type='text/javascript')
        if parsed.path == '/fixture.js':
            claims = base64.urlsafe_b64encode(json.dumps({'sub': 'local-only', 'exp': int(time.time()) + 86400, 'iss': 'https://cognito-idp.ap-southeast-1.amazonaws.com/local-only', 'client_id':'localfixture','token_use':'access','cognito:groups': []}).encode()).decode().rstrip('=')
            script = "const scenario=new URLSearchParams(location.search).get('scenario')||'empty';let token='fixture." + claims + ".not-a-signature';if(scenario==='admin'){const claims=JSON.parse(atob(token.split('.')[1]));claims['cognito:groups']=['admin'];token='fixture.'+btoa(JSON.stringify(claims))+'.not-a-signature';}if(sessionStorage.getItem('cloudhub.fixture.scenario')!==scenario){sessionStorage.clear();sessionStorage.setItem('cloudhub.fixture.scenario',scenario);if(scenario!=='guest')sessionStorage.setItem('cloudhub_access_token',token);}const banner=document.createElement('p');banner.id='fixture-banner';banner.textContent='KIỂM THỬ CỤC BỘ • DỮ LIỆU GIẢ LẬP • KHÔNG GỌI AWS • '+scenario;banner.setAttribute('role','status');document.body.prepend(banner);"
            return self.send(script, content_type='text/javascript')
        asset = parsed.path.lstrip('/') or 'index.html'
        if asset not in ASSETS:
            return self.send({'error': 'Asset not allowed'}, 404)
        source = (ROOT / 'frontend' / asset).read_text(encoding='utf-8')
        if asset == 'index.html':
            source = source.replace('CloudHub • Hạ tầng cloud theo nhu cầu', 'CloudHub • Kiểm thử cục bộ').replace('<script src="config.js">', '<script src="fixture.js"></script><script src="config.js">')
            # Reserve space for the fixture banner so the desktop sidebar remains visible.
            source = source.replace('</head>', '''<style>
              #fixture-banner { position:sticky; top:0; z-index:60; margin:0; padding:10px 16px;
                min-height:40px; line-height:20px; background:#fffbeb; color:#92400e; font-size:13px; }
              @media (min-width:769px) and (min-height:501px), (min-width:1025px) {
                .app-sidebar { top:40px; height:calc(100vh - 40px); }
                .content-section { scroll-margin-top:120px; }
              }
              .app-topbar { top:40px; }
              @media (max-width:768px), (max-width:1024px) and (max-height:500px) {
                .content-section { scroll-margin-top:80px; }
              }
            </style></head>''')
        return self.send(source, content_type={'html': 'text/html; charset=utf-8', 'css': 'text/css', 'js': 'text/javascript','json':'application/json'}[asset.split('.')[-1]])

    def do_PUT(self):
        return self.api('PUT',urlsplit(self.path).path)

    def do_POST(self):
        path = urlsplit(self.path).path
        if not path.startswith('/api/'):
            return self.send({'error': {'message': 'Only local fixture API accepted'}}, 403)
        return self.api('POST', path)

    def api(self, method, path):
        parts = path.split('/')
        name = parts[2]
        if name not in SCENARIOS:
            return self.send({'error': {'message': 'Unknown scenario'}}, 400)
        route = '/' + '/'.join(parts[3:])
        state = scenario_state(name)
        if name=='admin' and method=='GET' and route=='/admin/environments':
            return self.send({'items':[{**row,'owner_email':'student@example.invalid','owner_email_status':'FOUND'} for row in state['envs']]})
        if name=='admin' and method=='GET' and route=='/admin/users':
            from types import SimpleNamespace
            from cloudhub.admin_directory import users as directory_users
            from cloudhub.store import MemoryStore
            local_users=[{'owner_id':oid,'username':oid,'email':address,'enabled':True,'status':'CONFIRMED'} for oid,address in
                [('local-only','student@example.invalid'),('local-instructor','instructor@example.invalid'),('local-other','other@example.invalid')]]
            class LocalDirectory:
                def list(self,cursor=None):return {'items':local_users[2:] if cursor else local_users[:2],'next_cursor':None if cursor else 'local-page-2'}
            service=SimpleNamespace(store=MemoryStore(),limits=lambda owner:{'active':0,'max_active':2,'remaining_environments':2,'remaining_milliusd':10000,'user_budget_milliusd':10000})
            query={k:v[0] for k,v in parse_qs(urlsplit(self.path).query).items()}
            return self.send(directory_users(service,LocalDirectory(),query))
        if route.startswith('/admin/announcements'):
            if name!='admin':return self.send({'error':{'code':'FORBIDDEN'}},403)
            from cloudhub.errors import HubError
            body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0')))) if method!='GET' else {}
            key=self.headers.get('Idempotency-Key','local-fixture-command');bits=route.strip('/').split('/')
            try:
                if len(bits)==2:result=MAINTENANCE.listing() if method=='GET' else MAINTENANCE.create('local-admin',key,body)
                elif len(bits)==3:result=MAINTENANCE.view(MAINTENANCE.get(bits[2])) if method=='GET' else MAINTENANCE.edit('local-admin',bits[2],key,body)
                elif bits[3]=='preview':result=MAINTENANCE.preview('local-admin',bits[2],body)
                else:
                    action={'publish':MAINTENANCE.publish,'cancel':MAINTENANCE.cancel,'retry':MAINTENANCE.retry_sync}[bits[3]]
                    result=action('local-admin',bits[2],key,body);MAINTENANCE.sync_public(LocalNoticeWriter())
                return self.send(result,202 if len(bits)==4 and bits[3]!='preview' else 200)
            except HubError as exc:return self.send({'error':{'code':exc.code,'message':exc.message}},exc.status)
        if name=='notifications':
            if method=='GET' and route=='/notifications':
                items=state['notices'];active=[r for r in items if r['current']]
                return self.send({'items':active,'history':items,'unread_count':sum(not r['read_at'] for r in active),'warning_minutes':15})
            if method=='POST' and route.startswith('/notifications/') and route.endswith('/read'):
                row=next((r for r in state['notices'] if r['notification_id']==route.split('/')[2]),None)
                if row is None:return self.send({'error':{'code':'NOT_FOUND'}},404)
                row['read_at']=row['read_at'] or int(time.time());return self.send(row)
            if route=='/account/notification-preferences':
                if method=='POST':
                    body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))))
                    state['notification_preferences'].update(body,email_status='PENDING_CONFIRMATION' if body['email_enabled'] else 'DISABLED',masked_email='l***@example.invalid')
                return self.send(state['notification_preferences'])
            if method=='POST' and route=='/account/notification-preferences/check':
                # Synthetic status only. No subscription, email or AWS call.
                state['notification_preferences']['email_status']='CONFIRMED'
                return self.send(state['notification_preferences'])
        if (method,route) in {('GET','/recommendations/schema'),('POST','/recommendations')}:
            from cloudhub.service import Service
            from cloudhub.store import MemoryStore
            from cloudhub.cost import Estimator,RATE_REQUIREMENTS
            from cloudhub.recommendations import schema,recommend
            from cloudhub.errors import HubError
            fixture_rates={'approved':True,'region':'ap-southeast-1','updated_at':'LOCAL_FIXTURE_NOT_AWS_PRICES','units':{k:'0.01' for required in RATE_REQUIREMENTS.values() for k in required},'configuration_verifications':{configuration_key(t,configuration_profiles(t)[1]['configuration']):{'passed':True,'provisioning_checks':2,'backup_restore_verified':True} for t in ACTIVE_TEMPLATES}}
            fixture_rates['units']['cloudfront_functions_million']='0.1'
            svc=Service(MemoryStore(),estimator=Estimator(fixture_rates),verified=ACTIVE_TEMPLATES)
            try:
                value=schema(svc) if method=='GET' else recommend(svc,'local-only',json.loads(self.rfile.read(int(self.headers.get('Content-Length','0')))))
                value['local_fixture']=True
                return self.send(value)
            except HubError as exc:return self.send({'error':{'code':exc.code,'message':exc.message}},exc.status)
        if method=='GET' and route=='/public/catalog':
            from cloudhub.service import Service
            from cloudhub.store import MemoryStore
            from cloudhub.cost import Estimator,RATE_REQUIREMENTS
            from cloudhub.public_catalog import read
            from cloudhub.errors import HubError
            rates={'approved':True,'region':'ap-southeast-1','updated_at':'2026-10-18T00:00:00Z',
                'units':{k:'0.01' for required in RATE_REQUIREMENTS.values() for k in required}}
            rates['units']['cloudfront_functions_million']='0.01'
            rates['regional_rates']={region:{**rates,'region':region,'units':{k:value for k,value in rates['units'].items()}} for region in ('ap-northeast-1','us-east-1')}
            service=Service(MemoryStore(),estimator=Estimator(rates),verified=ACTIVE_TEMPLATES,user_limit=2,total_limit=4,budget_milliusd=10000,require_quotes=False)
            query={k:v[0] for k,v in parse_qs(urlsplit(self.path).query).items()}
            try:return self.send(read(service,query))
            except HubError as error:return self.send({'error':{'code':error.code}},error.status)
        if method=='PUT' and route=='/account/preferences':
            body=json.loads(self.rfile.read(int(self.headers.get('Content-Length','0'))));state['language_preference']=body['language'];return self.send({'language_preference':body['language']})
        if method == 'GET':
            responses = {'/account': {'email_verified': True, 'role': 'user','language_preference':state.get('language_preference','auto')}, '/templates': {'items': catalog(verified=ACTIVE_TEMPLATES,configuration_proofs={} if name=='unverified-config' else {configuration_key(t,configuration_profiles(t)[1]['configuration']):{'passed':True,'provisioning_checks':2,'backup_restore_verified':True,'mode':'LOCAL_SYNTHETIC_ONLY'} for t in ACTIVE_TEMPLATES})},
                         '/limits': {'active': len(state['envs']), 'max_active': 2, 'remaining_environments': 0 if name == 'quota' else max(0, 2-len(state['envs'])), 'remaining_milliusd': 2000, 'user_budget_milliusd': 10000},
                         '/notifications': {'items': []}, '/operations': {'items': list(state['ops'].values())}, '/environments': {'items': state['envs']}, '/recovery-points': {'items': []},
                         '/admin/environments':{'items':state['envs']},'/admin/users':{'items':[{'email':'student@example.invalid','username':'localstudent','owner_id':'local-only','region':'ap-southeast-1','enabled':True,'status':'CONFIRMED','limits':{'active':1,'max_active':2,'remaining_environments':1,'remaining_milliusd':2000,'user_budget_milliusd':10000}}],'next_cursor':None},
                         '/admin/signup-defaults':{'max_active':2,'budget_milliusd':10000},'/admin/notifications':{'status':'NOT_CONFIGURED','email':''}}
            if route=='/templates':
                from cloudhub.regions import RegionRegistry
                from cloudhub.cost import RATE_REQUIREMENTS
                fixture_rates={'approved':True,'region':'ap-southeast-1','units':{k:'0.01' for required in RATE_REQUIREMENTS.values() for k in required},'configuration_verifications':{configuration_key(t,configuration_profiles(t)[1]['configuration']):{'passed':True,'provisioning_checks':2,'backup_restore_verified':True} for t in ACTIVE_TEMPLATES}}
                registry=RegionRegistry('ap-southeast-1',fixture_rates)
                for item in responses['/templates']['items']:item.update(default_region='ap-southeast-1',regions=registry.options(item['template_id'],ACTIVE_TEMPLATES))
            if name=='wallet-platform':
                # Explicit synthetic balances for the personal/shared gate UI.
                responses['/limits'].update(user_remaining_milliusd=10000,remaining_milliusd=123,global_remaining_milliusd=123,
                    wallet={'schema':1,'currency':'USD','granted_milliusd':10000,'balance_milliusd':10000,'committed_milliusd':0},
                    platform_budget={'remaining_milliusd':123})
            if name=='unverified-user':
                responses['/account']={'email':'student@example.invalid','email_verified':False,'role':'user'}
            if name in {'ready','paused','admin'}:
                responses['/recovery-points']={'items':[{'recovery_point':'rp-local-backup','template_id':'T05','region':'ap-southeast-1','status':'AVAILABLE','scope':'GIẢ LẬP: EBS /data, không gồm root/RAM','retain_until':time.time()+7*86400,'restore_verified':True,'configuration':configuration_profiles('T05')[1]['configuration']}]}
            if name == 'loading' and route == '/templates':
                time.sleep(1)
            if name == 'long':
                env = {'environment_id': 'env-local-'+('long-'*12), 'template_id': 'T01', 'status': 'ERROR_RETAINED', 'needs_admin': True,
                       'operating_policy': {'mode': 'AUTO_RENEW', 'period_minutes': 60, 'ending_policy': 'PAUSE', 'budget_limit_milliusd': 10000}, 'deadline': int(time.time())+600, 'estimated_committed_milliusd': 999,
                       'cleanup_report': {'residual': [{'id': 'resource-long-'*25}], 'cost_note': 'Nội dung dài để kiểm tra khả năng đọc và bố cục trên điện thoại. '*12}}
                responses['/environments'] = {'items': [env]}
                responses['/operations'] = {'items': [{'operation_id': 'op-local-long-'*5, 'action': 'backup', 'status': 'FAILED', 'phase': 'BACKUP', 'error': 'Lỗi sao lưu GIẢ LẬP. Nguồn dữ liệu vẫn được giữ; xem thông báo và thử lại khi dịch vụ sẵn sàng. '*8, 'environment_id': env['environment_id']}]}
            if route.startswith('/operations/'):
                op=state['ops'].get(route.split('/')[-1])
                if name=='records' and op:op.update(status='SUCCEEDED',phase='DONE',updated_at=int(time.time()))
                return self.send(state['ops'].get(route.split('/')[-1], {'error': {'message': 'Fixture operation not found'}}))
            if route.startswith('/environments/'):
                if route.endswith('/template'):
                    # Synthetic DOM fixture only; never an AWS proof or a write.
                    from cloudhub.template_view import projection
                    template,resources,count,omitted=projection({'Resources':{'Machine':{'Type':'AWS::EC2::Instance','Properties':{'InstanceType':'t3.micro','UserData':'LOCAL_SYNTHETIC_HIDDEN'}},'Data':{'Type':'AWS::EC2::Volume','Properties':{'Size':8,'Encrypted':True,'VolumeType':'gp3'}}}})
                    return self.send({'environment_id':route.split('/')[2],'region':'ap-southeast-1','source':'AWS_CLOUDFORMATION_ORIGINAL','local_fixture':True,'read_only':True,'redacted':True,'deployable':False,'retrieved_at':int(time.time()),'template':template,'resources':resources,'redaction_count':count,'view_sha256':'0'*64,'omitted_sections':omitted})
                if name=='studio' and route.endswith('/files'):
                    return self.send({'items':[{'key':'index.html','size':100}], 'writes_used':1,'direct_upload_enabled':True,'write_enabled':True,
                                      'draft_release_id':'release-local-draft','active_release_id':'release-local-A','previous_release_id':'release-local-B',
                                      'limits':{'max_files':64,'max_file_bytes':1048576,'max_total_bytes':2097152}})
                if name=='files' and route=='/environments/env-local-existing/files':
                    return self.send({'items':[{'key':'mobile-fixture.txt','size':32}],'writes_used':1,
                                      'limits':{'max_files':64,'max_file_bytes':8192,'max_total_bytes':524288}})
                if route.endswith('/renewals'):
                    return self.send({'items':[{'operation_id':'op-local-renewal','automatic':False,'status':'SUCCEEDED','created_at':time.time()-600,'deadline':time.time()+3600,'period_estimate':{'total_milliusd':200}}],'total_count':1,'truncated':False})
                if len(route.split('/')) != 3:
                    return self.send({'error':{'message':'Thao tác này chưa được mô phỏng trong bản kiểm thử cục bộ.'}},404)
                env=next((env for env in state['envs'] if env['environment_id']==route.split('/')[2]),None)
                return self.send(env) if env else self.send({'error':{'message':'Fixture environment unavailable'}},404)
            return self.send(responses[route]) if route in responses else self.send({'error': {'message': 'Fixture endpoint unavailable'}}, 404)
        length = int(self.headers.get('Content-Length', '0'))
        if length > 65536:
            return self.send({'error': {'message': 'Fixture body too large'}}, 400)
        body = json.loads(self.rfile.read(length))
        if name=='records' and route.endswith(('/put_record','/list_records')):
            rows=state.setdefault('records',[])
            if route.endswith('/put_record'):
                rows[:]=[row for row in rows if row['record_id']!=body['record_id']]+[body]
            op={'operation_id':'op-local-record-'+str(len(state['ops'])+1),'action':route.split('/')[-1],'environment_id':'env-local-existing',
                'status':'RUNNING','phase':'USE_DATA','created_at':int(time.time()),'updated_at':int(time.time()),'result':{'items':list(rows)}}
            state['ops'][op['operation_id']]=op
            return self.send(op,202)
        if route.endswith('/management-estimate'):
            return self.send({'approved':True,'additional_commitment_milliusd':200,'cumulative_after_milliusd':654,'after_shutdown':{'total_milliusd':104,'period_hours':24},'unknown':['GIẢ LẬP CỤC BỘ — không đo chi phí AWS.']})
        if route == '/estimates':
            state['estimate_calls'] += 1
            if name == 'loading':
                time.sleep(2)
            if name == 'error' and state['estimate_calls'] == 1:
                return self.send({'error': {'message': 'Giá tạm thời chưa có (lỗi giả lập). Thử lấy dự toán lại.'}}, 503)
            quote=make_quote(body)
            if name=='unverified-config' and body.get('configuration')!=configuration(body['template_id']):
                quote['configuration_verified']=False
            return self.send(quote)
        if route == '/environments':
            state['create_calls'] += 1
            key = self.headers.get('Idempotency-Key')
            if name == 'submit-error' and state['create_calls'] == 1:
                return self.send({'error': {'message': 'Hạn mức vừa thay đổi (lỗi giả lập). Giữ cấu hình và lấy dự toán lại.'}}, 409)
            if key not in state['keys']:
                operation = {'operation_id': 'op-local-'+str(len(state['ops'])+1), 'action': 'create', 'status': 'RUNNING', 'phase': 'WAIT_CREATE', 'created_at': time.time()}
                state['keys'][key] = operation
                state['ops'][operation['operation_id']] = operation
                state['envs'].append({'environment_id': 'env-local-'+str(len(state['envs'])+1), 'template_id': body['template_id'], 'status': 'PROVISIONING', 'operating_policy': body['operating_policy'], 'estimate_hours': body['estimate_hours'], 'estimated_committed_milliusd': 454})
            if name == 'uncertain' and state['create_calls'] == 1:
                return self.send({'error': {'message': 'Mất phản hồi sau khi nhận tác vụ (lỗi giả lập).'}}, 503)
            return self.send(state['keys'][key], 202)
        return self.send({'error': {'message': 'Only creation fixture mutation supported'}}, 403)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--country',choices=['VN','JP','KR','CN','FR','DE','ES','US'],help='Explicit LOCAL simulated country; no IP geolocation')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    FIXTURE_COUNTRY=args.country
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'LOCAL SYNTHETIC FIXTURES ONLY http://127.0.0.1:{args.port}/?scenario=empty', flush=True)
    server.serve_forever()
