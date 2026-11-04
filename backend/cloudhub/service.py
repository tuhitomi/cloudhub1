"""F01/F03/F04: authorization, quota, durable commands and deadline fencing."""
import hashlib
import json
import re
import time
from copy import deepcopy
from .catalog import ACTIVE_TEMPLATES, S3_CONFIG, SCOPES, configuration, resolve_configuration, configuration_verified, configuration_key, configuration_profiles, environment_configuration
from .cost import Estimator
from .errors import HubError, Conflict
from .portal import PortalMixin
from .lifecycle import LifecycleMixin
from .operating_policy import validate_policy, legacy_policy, plan
from .regions import REGIONS
from .quotes import QuoteMixin
from .ledger import LedgerMixin, normalize
from .wallet import budget_refusal

def ident(prefix, *parts):
    return prefix + hashlib.sha256("|".join(parts).encode()).hexdigest()[:24]

def record(kind, entity_id, owner, **fields):
    return {"pk": kind[0].upper() + "#" + entity_id, "kind": kind, "owner_id": owner,
            "owner_sort": kind + "#" + entity_id, **fields}

def expected(*rows):
    return {r["pk"]: r.get("version") for r in rows}

def retry(fn):
    for _ in range(12):
        try:
            return fn()
        except Conflict:
            time.sleep(0.002)
    raise HubError("CONCURRENT_UPDATE", "Có yêu cầu đồng thời; hãy thử lại với cùng Idempotency-Key.", 409)

class Service(QuoteMixin, LedgerMixin, LifecycleMixin, PortalMixin):
    def __init__(self, store, clock=time.time, estimator=None, verified=None, validation=None,
                 user_limit=2, total_limit=4, budget_milliusd=0, workflow_terminal=None,price_provider=None,regions_config=None,regions_provider=None, require_quotes=True, continuous_enabled=False, direct_upload_enabled=False,catalog_price_provider=None,recommendations_enabled=False):
        self.store, self.clock = store, clock
        self.estimator = estimator or Estimator()
        self.verified = set(verified or []) & ACTIVE_TEMPLATES
        self.validation = set(validation or []) & ACTIVE_TEMPLATES
        self.user_limit, self.total_limit, self.budget = user_limit, total_limit, budget_milliusd
        self.workflow_terminal = workflow_terminal
        self.price_provider=price_provider
        self.catalog_price_provider=catalog_price_provider
        self.regions_config=regions_config or {}
        self.regions_provider=regions_provider
        self.require_quotes=require_quotes
        self.continuous_enabled=continuous_enabled
        self.direct_upload_enabled=direct_upload_enabled
        self.recommendations_enabled=recommendations_enabled

    def direct_upload_available(self,env):
        if not self.direct_upload_enabled or env.get('template_id') not in {'T02','T07'}:return False
        proof=self.regions_config.get('direct_upload_verifications',{}).get(self.region_for(env),{}).get(env['template_id'],{})
        required=['passed','backup_restore_verified','upload_verified','iam_reviewed']
        if env['template_id']=='T02':required.append('content_switch_verified')
        return all(proof.get(k) is True for k in required) and configuration_key(env['template_id'],env.get('configuration')) in proof.get('configuration_keys',[])

    def continuous_available(self,row):
        if not self.continuous_enabled:return False
        try:region=self.region_for(row)
        except HubError:return False
        proof=self.regions_config.get('continuous_verifications',{}).get(region,{}).get(row['template_id'],{})
        verified=self.continuous_enabled and all(proof.get(k) is True for k in ['passed','old_callback_verified','schedule_transition_verified','source_preservation_verified']) and configuration_key(row['template_id'],row.get('configuration')) in proof.get('configuration_keys',[])
        if row['template_id']=='T09':verified=verified and proof.get('read_api_schema_2_verified') is True and (row.get('kind')!='environment' or row.get('data_read_schema')==2)
        return bool(verified)

    def region_registry(self):
        from .regions import RegionRegistry
        return RegionRegistry(self.regions_config.get('control_region',self.estimator.rates.get('region','ap-southeast-1')),self.estimator.rates,self.regions_config)

    def region_options(self,tid):
        options=self.region_registry().options(tid,self.verified)
        for region in options:
            for profile in region['configuration_options']:
                if profile['id']=='files' and not self.direct_upload_available({'template_id':tid,'region':region['region'],'configuration':profile['configuration']}):
                    profile.update(create_enabled=False,status='UNAVAILABLE',disabled_reason='DIRECT_UPLOAD_DISABLED_OR_UNVERIFIED')
        return options

    def region_for(self,row):
        from .regions import record_region
        if row.get('kind') in {'operation','recovery'} and not row.get('region') and row.get('environment_id'):
            source=self.store.get('E#'+row['environment_id'])
            if source and source['owner_id']==row['owner_id']:
                return record_region({**row,'region':self.region_for(source)},self.regions_config)
        return record_region(row,self.regions_config)

    def estimator_for(self,row):
        region=self.region_for(row) if isinstance(row,dict) else row if row==self.region_registry().home else self.region_registry().select(row)
        return self.estimator.for_region(region)

    def refresh_region_policy(self):
        if self.regions_provider:self.regions_config=self.regions_provider()

    def refresh_pricing(self,cached=False):
        provider=self.catalog_price_provider if cached and self.catalog_price_provider else self.price_provider
        if provider:self.estimator=Estimator(provider())
        self.refresh_region_policy()

    def owned(self, kind, entity_id, owner):
        row = self.store.get(kind + "#" + entity_id)
        if not row or row.get("owner_id") != owner:
            raise HubError("NOT_FOUND", "Không tìm thấy tài nguyên thuộc tài khoản của bạn.", 404)
        return row

    def configuration_is_verified(self,tid,cfg,region=None):
        registry=self.region_registry()
        selected=registry.home if region is None else region
        if tid in {'T02','T07'} and any(p['id']=='files' and p['configuration']==cfg for p in configuration_profiles(tid)) and not self.direct_upload_available({'template_id':tid,'region':selected,'configuration':cfg}):return False
        return registry.verified(tid,cfg,registry.home if region is None or region==registry.home else registry.select(region),self.verified)

    def validate_create(self, body, is_admin=False):
        self.refresh_pricing()
        if set(body) - {"template_id", "duration_hours", "estimate_hours", "operating_policy", "configuration", "region", "recovery_point", "validation_run", "quote_id", "planning_workload", "application"}:
            raise HubError("INVALID_INPUT", "Trường không được phép; owner_id được lấy từ Cognito.")
        tid, hours = body.get("template_id"), body.get("duration_hours")
        if tid not in ACTIVE_TEMPLATES:
            raise HubError("TEMPLATE_UNAVAILABLE", "Mẫu không được cung cấp trong phạm vi hiện tại.", 409)
        validation_run = body.get("validation_run", False)
        if type(validation_run) is not bool:
            raise HubError("INVALID_INPUT", "validation_run phải là boolean.")
        if not (tid in self.verified or validation_run and is_admin and tid in self.validation):
            raise HubError("TEMPLATE_UNVERIFIED", "Mẫu chưa kiểm chứng AWS; chỉ quản trị được chạy vòng kiểm chứng đã duyệt.", 409)
        config=resolve_configuration(tid,body.get('configuration'))
        region=self.region_registry().select(body.get('region'))
        workload=body.get('planning_workload')
        if workload is not None:
            if not self.recommendations_enabled:raise HubError('RECOMMENDATIONS_DISABLED','Workload-aware admission is not enabled yet.',503)
            from .workloads import normalize,resource_assessment
            workload=normalize(tid,workload)
            preview_hours=body.get('estimate_hours',body.get('duration_hours',1))
            if type(preview_hours) is not int or not 1<=preview_hours<=8:raise HubError('INVALID_INPUT','Use an integer planning horizon from 1 to 8 hours.')
            if resource_assessment(tid,config,workload,hours=preview_hours)['status']=='NOT_FIT':
                raise HubError('WORKLOAD_CONFIGURATION_MISMATCH','The selected configuration does not meet the declared resource requirements.',409)
        permitted_validation=validation_run and is_admin and tid in self.validation and (region==self.region_registry().home or region in self.regions_config.get('validation_regions',[]))
        from .applications import validate_create as validate_application
        application=validate_application(self,tid,region,body,permitted_validation)
        if not self.configuration_is_verified(tid,config,region) and not permitted_validation:
            raise HubError('CONFIGURATION_UNVERIFIED','Lựa chọn cấu hình này đang chờ kiểm chứng AWS; cấu hình chuẩn vẫn dùng được.',409)
        if 'operating_policy' in body:
            if 'duration_hours' in body or 'estimate_hours' not in body:
                raise HubError('INVALID_INPUT','Dùng khoảng dự toán riêng và chính sách vận hành; không trộn duration_hours cũ.')
            policy=validate_policy(tid,body['operating_policy'])
            if policy['mode']=='CONTINUOUS' and not self.continuous_available({'template_id':tid,'region':region,'configuration':config}):
                raise HubError('CONTINUOUS_DISABLED','Continuous operation is not enabled by the administrator.',409)
            preview=body['estimate_hours']
            cost_plan=plan(self.estimator_for(region),tid,preview,policy,config,workload=workload)
            hours=(policy['period_minutes'] or preview*60)/60
        else:
            if 'estimate_hours' in body or type(hours) is not int or not 1<=hours<=8:
                raise HubError('INVALID_INPUT','Thời lượng tương thích cũ từ 1 đến 8 giờ.')
            cost_plan=plan(self.estimator_for(region),tid,hours,legacy_policy({'duration_hours':hours}),config,workload=workload)
        if tid=='T02' and self.direct_upload_available({'template_id':tid,'region':region,'configuration':config}) and 'cloudfront_functions_million' not in self.estimator_for(region).rates.get('units',{}):
            raise HubError('PRICES_UNAPPROVED','Review the global CloudFront Functions rate before enabling protected content releases.',409)
        cost_plan['region']=region
        if application is not None:cost_plan['application']=application
        if cost_plan['operating_policy']['mode']=='AUTO_RENEW' and (cost_plan['operating_policy']['budget_limit_milliusd']>self.budget
                or cost_plan['approved'] and (cost_plan['total_milliusd']>cost_plan['operating_policy']['budget_limit_milliusd'] or cost_plan['renewal_period']['total_milliusd']<=0)):
            raise HubError('CUMULATIVE_BUDGET_EXCEEDED','Giới hạn cộng dồn phải đủ kỳ đầu, hữu hạn và nằm trong ngân sách hệ thống.',409)
        quote = {**cost_plan["first_period"], "total_milliusd":cost_plan["total_milliusd"]}
        if not quote["approved"]:
            raise HubError("PRICES_UNAPPROVED", "Cần phê duyệt đơn giá và region trước khi tạo.", 409)
        return tid, hours, quote, cost_plan

    def idempotency(self, owner, key, scope, body):
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,100}", key):
            raise HubError("IDEMPOTENCY_KEY_REQUIRED", "Cần Idempotency-Key dài 8–100 ký tự chữ, số, _ hoặc -.")
        pk = "I#" + ident("", owner, scope, key)
        fingerprint = hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        old = self.store.get(pk)
        if old and old["fingerprint"] != fingerprint:
            raise HubError("IDEMPOTENCY_MISMATCH", "Khóa này đã được dùng cho nội dung khác.", 409)
        return pk, fingerprint, old

    def quota(self, owner, amount, increase=1):
        user = self.store.get("Q#" + owner) or {"pk": "Q#" + owner, "active": 0}
        glob = self.store.get("Q#GLOBAL") or {"pk": "Q#GLOBAL", "active": 0, "reserved_milliusd": 0}
        if increase > 0 and (user["active"] + increase > user.get('max_active',self.user_limit) or glob["active"] + increase > self.total_limit):
            raise HubError("QUOTA_EXCEEDED", "Đã đạt quota môi trường.", 409)
        refusal=budget_refusal(self,user,glob,amount) if amount>0 else None
        if refusal:
            raise HubError("BUDGET_EXCEEDED", "Ví dự toán không đủ." if refusal['budget_scope']=='ACCOUNT_WALLET' else "Ngân sách chung của nền tảng không đủ; số dư ví cá nhân được giữ nguyên.", 409, refusal)
        normalize(user,int(self.clock()));normalize(glob,int(self.clock()))
        user["future_reserved_milliusd"]+=amount;glob["future_reserved_milliusd"]+=amount
        user["ledger_updated_at"]=glob["ledger_updated_at"]=int(self.clock())
        user["active"] += increase
        glob["active"] += increase
        glob["reserved_milliusd"] += amount
        user['reserved_milliusd'] = user.get('reserved_milliusd',0)+amount
        return user, glob

    def create(self, owner, key, body, is_admin=False):
        request_body=deepcopy(body)
        _,_,previous=self.idempotency(owner,key,'create',request_body)
        if previous:return self.owned('O',previous['operation_id'],owner)
        if body.get('recovery_point'):
            from .applications import restore_inputs
            body=restore_inputs(self,owner,body)
        if body.get('recovery_point') and 'configuration' not in body:
            source=self.owned('R',body['recovery_point'],owner)
            body={**body,'configuration':environment_configuration(source)}
        if body.get('recovery_point') and 'region' not in body:
            body={**body,'region':self.region_for(self.owned('R',body['recovery_point'],owner))}
        tid, hours, quote, cost_plan = self.validate_create(body, is_admin)
        from decimal import Decimal
        hours=Decimal(cost_plan["operating_policy"]["period_minutes"] or cost_plan["estimate_hours"]*60)/60
        def transaction():
            ipk, fp, old = self.idempotency(owner, key, "create", request_body)
            if old:
                return self.owned("O", old["operation_id"], owner)
            now = int(self.clock())
            eid, oid = ident("env-", ipk), ident("op-", ipk)
            backup = None
            if body.get("recovery_point"):
                backup = self.owned("R", body["recovery_point"], owner)
                if backup["status"] != "AVAILABLE" or backup["retain_until"] <= now or backup.get("restore_lock") or backup.get('export_lock') or backup.get('delete_lock'):
                    raise HubError("RECOVERY_UNAVAILABLE", "Bản sao chưa sẵn sàng, hết hạn hoặc đang được khôi phục.", 409)
                if backup["template_id"] != tid:
                    raise HubError("INVALID_RECOVERY", "Bản sao thuộc mẫu khác.")
                if environment_configuration(backup)!=cost_plan['configuration']:
                    raise HubError('RECOVERY_CONFIGURATION_MISMATCH','Khôi phục giữ đúng cấu hình nguồn; không đổi kích thước hoặc thu nhỏ dữ liệu.',409)
                if self.region_for(backup)!=cost_plan['region']:
                    raise HubError('RECOVERY_REGION_MISMATCH','Restore in the original Region. Cross-Region migration is not supported.',409)
            user, glob = self.quota(owner, quote["total_milliusd"])
            env = record("environment", eid, owner, environment_id=eid, template_id=tid,
                status="PROVISIONING", duration_hours=hours, created_at=now, deadline=None,
                lock=oid, estimate=quote, resources=[], restore_from=body.get("recovery_point"),
                validation_run=body.get("validation_run", False), quota_released=False,
                operating_schema=2, operating_policy=cost_plan['operating_policy'], lifecycle_revision=1,
                schedule_pending=True, estimate_hours=cost_plan['estimate_hours'], cost_plan=cost_plan,
                first_period_estimate=cost_plan['first_period'], estimated_committed_milliusd=quote['total_milliusd'],
                retirement_allowance_committed=cost_plan['operating_policy']['ending_policy']=='BACKUP_RETIRE',
                pause_holding_allowance_committed=cost_plan['operating_policy']['ending_policy']=='PAUSE',
                renewal_count=0)
            if cost_plan.get('planning_workload') is not None:env['planning_workload']=cost_plan['planning_workload']
            if cost_plan.get('application'):
                env['application']=cost_plan['application'];env['application_revision']=cost_plan['application']['revision'];env['application_history']=[];env['application_template_schema']=2
            if tid=='T09':env['data_read_schema']=2
            if tid=='T02' and self.direct_upload_available({'template_id':tid,'region':cost_plan['region'],'configuration':cost_plan['configuration']}):env['direct_upload_schema']=1
            env.update(configuration=cost_plan['configuration'],configuration_schema=1,region=cost_plan['region'],region_provenance='validated_create')
            op = record("operation", oid, owner, operation_id=oid, job_id=oid, environment_id=eid,
                action="restore" if backup else "create", status="QUEUED", phase="CREATE", created_at=now,
                attempts=0, events=[], region=env['region'],recovery_point=body.get("recovery_point"))
            idem = {"pk": ipk, "fingerprint": fp, "operation_id": oid}
            rows = [user, glob, env, op, idem]
            terms_estimate={**cost_plan, "configuration_verified":True, "budget_feasible":True}
            rows.extend(self.consume_quote(owner,body.get("quote_id"),"restore" if backup else "create",self.create_quote_inputs(body,cost_plan),terms_estimate,oid))
            if backup:
                backup["restore_lock"] = oid
                rows.append(backup)
            rows.extend(self.accounting_reservation(op,env,rows))
            self.store.commit(rows, expected(*rows))
            return self.store.get(op["pk"])
        return retry(transaction)

    def command(self, owner, eid, action, key, body=None, due=False, admin_actor=None, reason=None):
        body = body or {}
        if set(body)-({"quote_id","confirmed","expected_revision"} if action=='destroy' else {"quote_id"}) or action not in {"backup", "destroy", "audit"}:
            raise HubError("INVALID_INPUT", "Tác vụ không hợp lệ hoặc có trường không được phép.")
        def transaction():
            env = self.owned("E", eid, owner)
            _,_,old=self.idempotency(owner,key,eid+'/'+action,{'actor':admin_actor,'reason':reason} if admin_actor else body)
            if old:return self.owned('O',old['operation_id'],owner)
            quotes=[]
            if action=='destroy' and not admin_actor and not due:
                ipk,_,_=self.idempotency(owner,key,eid+'/'+action,body)
                quotes=self.consume_termination(owner,env,action,body,ident('op-',ipk))
            if action=='backup' and not admin_actor and not due:
                estimate=self.management_estimate(owner,eid,{'action':action},issue=False)
                ipk,_,_=self.idempotency(owner,key,eid+'/'+action,body)
                quotes=self.consume_quote(owner,body.get('quote_id'),action,{'action':action},estimate,ident('op-',ipk),env)
            return self._enqueue_command(env, owner, eid, action, key, body, due, admin_actor, reason,extra_rows=quotes)
        return retry(transaction)

    def _enqueue_command(self, env, owner, eid, action, key, body, due=False, admin_actor=None, reason=None, extra_rows=None,idempotency_scope=None):
        ipk, fp, old = self.idempotency(owner, key, eid + "/" + (idempotency_scope or action), {'actor':admin_actor,'reason':reason} if admin_actor else body)
        if old:
            return self.owned("O", old["operation_id"], owner)
        now = int(self.clock())
        if due and (env["status"] != "READY" or (env.get("deadline") is None or env["deadline"] > now)):
            return None
        if env.get("lock"):
            raise HubError("OPERATION_LOCKED", "Môi trường đang có tác vụ.", 409)
        allowed = {"backup": {"READY"}, "destroy": {"READY", "PAUSED", "ERROR_RETAINED", "CREATE_FAILED"},
                   "audit": {"DELETED", "RESIDUAL", "ERROR_RETAINED", "CREATE_FAILED"}}
        if action=='destroy' and env.get('publication_uncertain'):
            raise HubError('PUBLICATION_RECONCILIATION_REQUIRED','Reconcile or retry the content switch before backing up and retiring this website.',409)
        proof=env.get('missing_uncreated_source',{})
        failed_missing_data=(env['template_id']=='T09' and not env.get('ready_at')
            and proof.get('type')=='AWS::DynamoDB::Table' and proof.get('id')=='cloudhub-'+eid+'-data'
            and proof.get('error')=='ResourceNotFoundException'
            and proof.get('failed_stack_status') in {'CREATE_FAILED','ROLLBACK_COMPLETE','ROLLBACK_FAILED'}
            and not (env.get('instance_id') or env.get('bucket_name') or env.get('source_ids')))
        if failed_missing_data:allowed['destroy'].add('RESIDUAL')
        if env["status"] not in allowed[action]:
            raise HubError("INVALID_STATE", "Trạng thái không cho phép tác vụ này.", 409)
        if action=='destroy' and not env.get('retirement_allowance_committed',True):
            # Never block a cost-reducing retirement on pricing/quota. Preserve the
            # unpriced exposure for reconciliation; do not invent a zero reservation.
            env['retirement_cost_reconciliation_required']=True
        oid = ident("op-", ipk)
        rp = ident("rp-", oid) if action in {"backup", "destroy"} else None
        op = record("operation", oid, owner, operation_id=oid, job_id=oid, environment_id=eid,
            action=action, status="QUEUED", phase="AUDIT" if action == "audit" else "BACKUP",
            created_at=now, attempts=0, events=[], region=self.region_for(env), recovery_point=rp)
        if admin_actor:
            op.update(admin_actor=admin_actor,admin_reason=reason)
        if action=='destroy':
            op['termination_data_policy']={'ending_policy':'BACKUP_RETIRE','retention_days':7,
                'mandatory_backup':True,'additional_costs_possible':True,
                'authority':'ADMIN_REASON' if admin_actor else 'EXISTING_AUTOMATIC_POLICY' if due else 'USER_DATA_CONSENT'}
        # Failed provisioning with no instance may be cleaned without backing up nonexistent data.
        if action == "destroy" and (env["status"] == "CREATE_FAILED" or failed_missing_data) and not (env.get("instance_id") or env.get("bucket_name") or env.get("source_ids")):
            op["phase"], op["recovery_point"] = "DELETE", None
            rp = None
        if action=="destroy" and env["status"]=="PAUSED":op["phase"]="START_FOR_RETIRE"
        env["lock"] = oid
        if due:
            env["expiry_triggered_at"] = env.get("expiry_triggered_at", now)
        env["status"] = {"backup": "BACKING_UP", "destroy": "RETIRING", "audit": env["status"]}[action]
        rows = [env, op, {"pk": ipk, "fingerprint": fp, "operation_id": oid}]+list(extra_rows or [])
        if action=='destroy' and env.get('retirement_cost_reconciliation_required'):
            rows.append(record('ledger_exposure',oid,owner,environment_id=eid,operation_id=oid,
                region=self.region_for(env),created_at=now,amount_milliusd=None,is_aws_actual=False,
                reason='UNPRICED_MANDATORY_RETENTION_ON_COST_REDUCTION',data_policy=op['termination_data_policy']))
        if due:op.update(auto_termination=True,ending_policy="BACKUP_RETIRE")
        if action=='destroy':env["lifecycle_revision"]=int(env.get("lifecycle_revision",0))+1
        if action == "backup":
            # Extra backups reserve a full session estimate conservatively.
            quote = self.estimator_for(env).estimate(env["template_id"], 1,configuration=environment_configuration(env),workload=env.get('planning_workload'))
            if not quote["approved"]:
                raise HubError("PRICES_UNAPPROVED", "Chưa phê duyệt chi phí bản sao.", 409)
            user, glob = self.quota(owner, quote["total_milliusd"], 0)
            env['estimated_committed_milliusd']=self._committed(env)+quote['total_milliusd']
            env['estimate']['total_milliusd']=env['estimated_committed_milliusd']
            counter = self.store.get("B#" + eid) or {"pk": "B#" + eid, "count": 0}
            if counter["count"] >= 3:
                raise HubError("BACKUP_QUOTA", "Tối đa 3 bản sao thủ công cho một môi trường.", 409)
            counter["count"] += 1
            rows.extend([user, glob, counter])
        if rp:
            rows.append(record("recovery", rp, owner, recovery_point=rp, environment_id=eid,
                template_id=env["template_id"], status="PENDING", source=env.get('data_source') or env.get("bucket_name") or env.get("data_volume_id"),
                created_at=now, retain_until=now + 7 * 86400,
                scope=SCOPES[env['template_id']],
                configuration=environment_configuration(env),configuration_schema=1,region=self.region_for(env),
                restore_verified=False, retirement_lock=oid if action == 'destroy' else None))
        rows.extend(self.accounting_reservation(op,env,rows))
        self.store.commit(rows, expected(*rows))
        return self.store.get(op["pk"])

    def data_command(self, owner, eid, action, key, body):
        if action not in {'put_record','list_records','load_dataset','query_demo'}:
            raise HubError('INVALID_INPUT','Tác vụ dữ liệu không được hỗ trợ.')
        if action in {'put_record','load_dataset'}:
            if set(body)!={'record_id','text'} or not isinstance(body['record_id'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',body['record_id']) or not isinstance(body['text'],str) or len(body['text'].encode())>256 or any(ord(c)<32 and c not in '\n\t' for c in body['text']):
                raise HubError('INVALID_INPUT','record_id tối đa 64 ký tự; text tối đa 256 byte, không có ký tự điều khiển.')
        elif body:
            raise HubError('INVALID_INPUT','Tác vụ đọc dữ liệu dùng object rỗng.')
        def transaction():
            env=self.owned('E',eid,owner)
            supported={'T03':{'put_record','list_records'},'T04':{'put_record','list_records'},'T08':{'put_record','list_records'},'T09':{'put_record','list_records'},'T10':{'load_dataset','query_demo'}}
            if action not in supported.get(env['template_id'],set()):raise HubError('UNSUPPORTED_OPERATION','Mẫu không hỗ trợ tác vụ dữ liệu này.',409)
            ipk,fp,old=self.idempotency(owner,key,eid+'/'+action,body)
            if old:return self.owned('O',old['operation_id'],owner)
            if env['status']!='READY' or env.get('lock') or (env.get('deadline') is not None and env['deadline']<=int(self.clock())):raise HubError('OPERATION_LOCKED','Môi trường hết hạn hoặc đang có tác vụ.',409)
            if env.get('data_commands',0)>=128:raise HubError('DATA_QUOTA','Tối đa 128 tác vụ dữ liệu mỗi phiên.',409)
            oid=ident('op-',ipk);env['lock']=oid;env['data_commands']=env.get('data_commands',0)+1
            op=record('operation',oid,owner,operation_id=oid,job_id=oid,environment_id=eid,action=action,status='QUEUED',phase='USE_DATA',
                created_at=int(self.clock()),attempts=0,events=[],region=self.region_for(env),data=deepcopy(body))
            rows=[env,op,{'pk':ipk,'fingerprint':fp,'operation_id':oid}]
            self.store.commit(rows,expected(*rows));return self.store.get(op['pk'])
        return retry(transaction)

    def write_file(self, owner, eid, key, body):
        from .s3_files import validate_file
        validate_file(body)
        def transaction():
            env = self.owned("E", eid, owner)
            ipk, fp, old = self.idempotency(owner, key, eid + "/files", body)
            if old:
                return self.owned("O", old["operation_id"], owner)
            if env['template_id']=='T02' and env.get('direct_upload_schema')==1:raise HubError('RELEASE_REQUIRED','Use a prepared website release.',409)
            if env["template_id"] not in {'T02','T06','T07'}:
                raise HubError("UNSUPPORTED_OPERATION", "Mẫu này không dùng kho file S3.", 409)
            if env["status"] != "READY" or env.get("lock") or (env.get("deadline") is not None and env["deadline"] <= int(self.clock())):
                raise HubError("OPERATION_LOCKED", "Môi trường hết hạn hoặc đang có tác vụ; chưa thể đăng file.", 409)
            if env.get("file_writes", 0) >= S3_CONFIG["max_writes"]:
                raise HubError("FILE_QUOTA", "Đã đạt giới hạn số lần đăng file trong phiên.", 409)
            oid = ident("op-", ipk)
            env["lock"], env["file_writes"] = oid, env.get("file_writes", 0) + 1
            op = record("operation", oid, owner, operation_id=oid, job_id=oid, environment_id=eid,
                action="write_file", status="QUEUED", phase="WRITE_FILE", created_at=int(self.clock()),
                attempts=0, events=[], region=self.region_for(env),file=deepcopy(body))
            rows = [env, op, {"pk": ipk, "fingerprint": fp, "operation_id": oid}]
            self.store.commit(rows, expected(*rows))
            return self.store.get(op["pk"])
        return retry(transaction)

    def extend(self, owner, eid, key, body):
        if set(body)-{'hours','quote_id'} or 'hours' not in body or type(body['hours']) is not int or not 1<=body['hours']<=4:
            raise HubError('INVALID_INPUT','Gia hạn tương thích từ 1 đến 4 giờ.')
        return self.renew(owner,eid,key,{'minutes':body['hours']*60,'confirmed':True,**({'quote_id':body['quote_id']} if 'quote_id' in body else {})})

    def save(self, *rows):
        # Propagate persisted location inside every transaction, including retries
        # and recovery points created by lifecycle/product mixins.
        for row in rows:
            if row.get('kind') in {'operation','environment'}:row['updated_at']=int(self.clock())
            if row.get('kind') in {'operation','recovery'} and not row.get('region'):
                source=next((r for r in rows if r.get('kind')=='environment' and r.get('environment_id')==row.get('environment_id')),None)
                source=source or self.store.get('E#'+row['environment_id'])
                if source and source.get('region'):row['region']=source['region']
        self.store.commit(list(rows), expected(*rows))

    def retirement_recovery(self, op, env):
        """Fence legacy points too before any irreversible source deletion."""
        rp = self.store.get('R#' + op['recovery_point'])
        if (not rp or rp['status'] != 'AVAILABLE' or rp['retain_until'] <= self.clock()
                or rp.get('owner_id') != env['owner_id']
                or rp.get('environment_id') != env['environment_id']
                or rp.get('delete_lock')
                or rp.get('retirement_lock') not in {None, op['operation_id']}):
            raise HubError('FINAL_BACKUP_UNAVAILABLE',
                           'Bản sao cuối cùng không còn hợp lệ. Giữ nguồn; tạo tác vụ thu hồi mới để sao lưu lại.', 409)
        if not rp.get('retirement_lock'):
            rp['retirement_lock'] = op['operation_id']
            self.save(rp)
        return rp

    def finish(self, op, env, status="SUCCEEDED"):
        op["status"], op["finished_at"] = status, int(self.clock())
        env["lock"] = None
        if status=='SUCCEEDED' and op['action'] in {'create','restore','backup','write_file','commit_upload','publish_release','put_record','list_records','load_dataset','query_demo'}:
            env['status']='READY';env['needs_admin']=False
        rows = [op, env]
        from .notifications import operation_notices
        rows.extend(operation_notices(self, op, env, status))
        if env['status'] == 'DELETED':
            # Failed/cancelled retirement points stay protected until a later
            # retirement or audit confirms that no source resources remain.
            for rp in self.store.scan_kind('recovery'):
                if rp['environment_id'] == env['environment_id'] and rp.get('retirement_lock'):
                    rp['retirement_lock'] = None
                    rows.append(rp)
        if op["action"] == "restore":
            rp = self.store.get("R#" + op["recovery_point"])
            rp["restore_lock"] = None
            if status == "SUCCEEDED":
                rp["restore_verified"] = True
                rp["verified_environment_id"] = env["environment_id"]
                rp["verified_at"] = int(self.clock())
            rows.append(rp)
        if env["status"] == "DELETED" and not env["quota_released"]:
            user, glob = self.quota(env["owner_id"], 0, -1)
            env["quota_released"] = True
            rows.extend([user, glob])
        settled=self.settlement_rows(env,rows)
        by_key={r['pk']:r for r in [*rows,*settled]}
        self.save(*by_key.values())
