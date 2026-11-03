"""Product controls; every mutation is fenced with the existing durable store."""
from copy import deepcopy
from .errors import HubError
from .wallet import snapshot as wallet_snapshot

RETRY_PHASES = {'READINESS', 'SCHEDULE', 'BACKUP', 'RESUME', 'WAIT_RESUME',
                'DELETE', 'AUDIT', 'WRITE_FILE', 'USE_DATA', 'DELETE_BACKUP',
                'EXPORT_BACKUP', 'COST','SYNC_SCHEDULE','PAUSE','PAUSE_AUDIT','CANCEL_SCHEDULE',
                'COMMIT_UPLOAD','PUBLISH_RELEASE','DEPLOY_APPLICATION','START_RESTART','WAIT_RESTART','START_FOR_RETIRE','WAIT_RETIRE_READY'}

class PortalMixin:
    def limits(self, owner):
        user = self.store.get('Q#' + owner) or {}
        glob = self.store.get('Q#GLOBAL') or {}
        limit = int(user.get('max_active', self.user_limit))
        wallet=wallet_snapshot(self,user)
        budget=wallet['granted_milliusd']
        platform_remaining=max(0,self.budget-int(glob.get('reserved_milliusd',0))-int(glob.get('observed_unreserved_milliusd',0)))
        return {'active': int(user.get('active', 0)), 'max_active': limit,
                'remaining_environments': max(0, min(limit-int(user.get('active',0)), self.total_limit-int(glob.get('active',0)))),
                'user_reserved_milliusd': int(user.get('reserved_milliusd',0)),
                'user_budget_milliusd': budget,
                # Legacy clients keep the effective admission amount. New UI
                # uses wallet.balance_milliusd and displays the platform gate separately.
                'remaining_milliusd': min(wallet['balance_milliusd'],platform_remaining),
                'user_remaining_milliusd':wallet['balance_milliusd'],'wallet':wallet,
                'platform_budget':{'remaining_milliusd':platform_remaining,'scope':'SHARED_AWS_FORECAST','is_aws_credits':False},
                'global_remaining_environments': max(0,self.total_limit-int(glob.get('active',0))),
                'global_remaining_milliusd': max(0,self.budget-int(glob.get('reserved_milliusd',0))-int(glob.get('observed_unreserved_milliusd',0))),
                'budget_method': 'Forecast reservations + elapsed estimates + unreconciled legacy; not AWS billing or credits',
                'budget_cycle':'PROJECT_LIFETIME',
                'forecast':{'future_reserved_milliusd':int(user.get('future_reserved_milliusd',0)),
                    'accrued_estimate_milliusd':int(user.get('accrued_estimate_milliusd',0)),
                    'legacy_unallocated_milliusd':int(user.get('legacy_unallocated_milliusd',user.get('reserved_milliusd',0) if user.get('ledger_schema')!=2 else 0)),
                    'released_estimate_milliusd':int(user.get('released_estimate_milliusd',0)),
                    'observed_unreserved_milliusd':int(user.get('observed_unreserved_milliusd',0)),
                    'updated_at':user.get('ledger_updated_at'), 'currency':'USD'},
                'aws_actual':{'amount_milliusd':None,'status':'USE_ENVIRONMENT_COST_REPORT','checked_at':None},
                'retained_resource_costs':'See each environment cleanup report; retained assets can incur charges beyond forecast allowances'}

    def set_limits(self, actor, owner, body):
        from .service import retry, expected
        if set(body) != {'max_active','budget_milliusd'} or type(body['max_active']) is not int or not 0 <= body['max_active'] <= self.total_limit or type(body['budget_milliusd']) is not int or not 0 <= body['budget_milliusd'] <= self.budget:
            raise HubError('INVALID_INPUT','Hạn mức phải nằm trong hạn mức toàn hệ thống.')
        if owner == 'GLOBAL' or not owner:
            raise HubError('INVALID_INPUT','Người dùng không hợp lệ.')
        def commit():
            row=self.store.get('Q#'+owner) or {'pk':'Q#'+owner,'active':0,'reserved_milliusd':0}
            row.update(body,updated_by=actor,updated_at=int(self.clock()))
            from .service import record,ident
            previous=wallet_snapshot(self,self.store.get('Q#'+owner) or {})
            audit=record('wallet_adjustment',ident('wallet-',owner,actor,str(row.get('version',0)),str(body['budget_milliusd'])),owner,
                actor=actor,created_at=int(self.clock()),previous_granted_milliusd=previous['granted_milliusd'],
                granted_milliusd=body['budget_milliusd'],reason='ADMIN_CREDIT_LIMIT_SET',is_aws_actual=False)
            self.store.commit([row,audit],expected(row,audit))
            return self.limits(owner)
        return retry(commit)

    def notifications(self, owner):
        from .notifications import NotificationCenter
        return NotificationCenter(self).list(owner)

    def remind(self, eid):
        from .notifications import NotificationCenter
        return NotificationCenter(self).remind(eid)

    def control_operation(self, owner, oid, action, key, body,automatic=False,check_only=False):
        from .service import retry, expected, record, ident
        if body or action not in {'retry','cancel'}:
            raise HubError('INVALID_INPUT','Thao tác tác vụ không hợp lệ.')
        def commit():
            op=self.owned('O',oid,owner)
            ipk,fp,old=self.idempotency(owner,key,oid+'/'+action,{})
            if old and not check_only:return self.owned('O',oid,owner)
            if op['status']!='FAILED':
                raise HubError('INVALID_STATE','Chỉ thử lại hoặc đóng tác vụ đã thất bại; tác vụ đang chạy phải hoàn tất trước.',409)
            if self.workflow_terminal and not self.workflow_terminal(op):
                raise HubError('WORKFLOW_RUNNING','Workflow vẫn đang kết thúc. Thử lại sau ít giây.',409)
            env=self.owned('E',op['environment_id'],owner)
            if env.get('lock'):
                raise HubError('OPERATION_LOCKED','Môi trường đang có tác vụ khác.',409)
            rows=[op,{'pk':ipk,'fingerprint':fp,'operation_id':oid}]
            if action=='cancel':
                if op['action']=='publish_release' and not op.get('cf_switch_attempted'):
                    env.update(publication_uncertain=False,status='READY');rows.append(env)
                op.update(status='CANCELLED',cancelled_at=int(self.clock()),cancel_note='Đóng tác vụ lỗi; giữ nguyên dữ liệu và tài nguyên. Thu hồi là thao tác riêng.')
            else:
                phase=op.get('failed_phase',op['phase'])
                construction_retry=(phase in {'CREATE','WAIT_CREATE'} and op['action']=='create'
                        and env['template_id'] in {'T03','T04','T06','T08','T09'})
                if construction_retry:
                    phase='CREATE'
                if (phase not in RETRY_PHASES and not construction_retry) or (op.get('automatic_retries',0)>=2 if automatic else op.get('manual_retries',0)>=3):
                    raise HubError('RETRY_UNAVAILABLE','Không thể thử lại bước này. Kiểm tra/thu hồi nguồn trước khi tạo mới, hoặc đã đạt 3 lần thử.',409)
                rp=self.store.get('R#'+op['recovery_point']) if op.get('recovery_point') else None
                if op['action'] in {'delete_backup','export_backup'}:
                    if not rp or rp.get('restore_lock') or rp.get('export_lock') or rp.get('delete_lock') or op['action']=='delete_backup' and rp.get('retirement_lock'):
                        raise HubError('RECOVERY_LOCKED','Bản sao đang được sử dụng.',409)
                    if op['action']=='export_backup' and (rp['status']!='AVAILABLE' or rp['retain_until']<=self.clock()):
                        raise HubError('RECOVERY_UNAVAILABLE','Bản sao không còn cho tải.',409)
                    rp['delete_lock' if op['action']=='delete_backup' else 'export_lock']=oid
                    if op['action']=='delete_backup':rp['status']='DELETING'
                elif op['action']=='cost':
                    if env.get('cost_lock'):raise HubError('OPERATION_LOCKED','Đang có đối soát khác.',409)
                    env['cost_lock']=oid;rows.append(env)
                else:
                    if env['status']=='DELETED' and op['action']!='audit' and op['action']!='cost':
                        raise HubError('INVALID_STATE','Nguồn đã thu hồi, không thử lại thao tác dữ liệu.',409)
                    env['lock']=oid
                    if op['action']=='destroy' and phase=='DELETE' and op.get('recovery_point'):
                        if (not rp or rp['status']!='AVAILABLE' or rp['retain_until']<=self.clock()
                                or rp.get('delete_lock') or rp.get('owner_id')!=owner
                                or rp.get('environment_id')!=env['environment_id']
                                or rp.get('retirement_lock') not in {None,oid}):
                            raise HubError('FINAL_BACKUP_UNAVAILABLE','Bản sao cuối cùng không còn hợp lệ. Giữ nguồn; tạo tác vụ thu hồi mới để sao lưu lại.',409)
                        rp['retirement_lock']=oid
                    if op['action']=='restore':
                        if not rp or rp['status']!='AVAILABLE' or rp['retain_until']<=self.clock() or rp.get('restore_lock') or rp.get('export_lock') or rp.get('delete_lock'):
                            raise HubError('RECOVERY_UNAVAILABLE','Không thể dùng lại bản sao.',409)
                        rp['restore_lock']=oid
                    env['status']={'backup':'BACKING_UP','destroy':'RETIRING','create':'PROVISIONING','restore':'PROVISIONING'}.get(op['action'],env['status'])
                    rows.append(env)
                if rp:rows.append(rp)
                if phase=='BACKUP' and op['action'] in {'backup','destroy'}:
                    # A resumed source may have changed. Never reuse its old checksum,
                    # file cursor or native snapshot for the next retirement attempt.
                    from .catalog import SCOPES,environment_configuration
                    configuration=environment_configuration(env)
                    if op['action']=='destroy':
                        # Preserve the accepted mandatory data policy. A price
                        # outage/full forecast cannot strand a billable source.
                        # Additional retention is an auditable unknown, never a
                        # fabricated zero/refund or a waived backup obligation.
                        env['retirement_cost_reconciliation_required']=True
                        rows.append(record('ledger_exposure',ident('retry-',oid,str(op.get('generation',0)+1)),owner,
                            environment_id=env['environment_id'],operation_id=oid,region=self.region_for(env),created_at=int(self.clock()),
                            amount_milliusd=None,is_aws_actual=False,reason='UNPRICED_MANDATORY_RETENTION_RETRY',
                            data_policy=op.get('termination_data_policy',{'ending_policy':'BACKUP_RETIRE','mandatory_backup':True,'retention_days':7,'authority':'ACCEPTED_LEGACY_RETIREMENT'})))
                    else:
                        quote=self.estimator_for(env).estimate(env['template_id'],1,configuration=configuration)
                        if not quote['approved']:raise HubError('PRICES_UNAPPROVED','Chưa phê duyệt dự toán bản sao.',409)
                        rows.extend(self.quota(owner,quote['total_milliusd'],0))
                        env['estimated_committed_milliusd']=self._committed(env)+quote['total_milliusd']
                        env['estimate']['total_milliusd']=env['estimated_committed_milliusd']
                    rid=ident('rp-',oid,'retry',str(op.get('generation',0)+1));now=int(self.clock())
                    fresh=record('recovery',rid,owner,recovery_point=rid,environment_id=env['environment_id'],template_id=env['template_id'],configuration=configuration,configuration_schema=1,region=self.region_for(env),status='PENDING',source=env.get('data_source') or env.get('bucket_name') or env.get('data_volume_id'),created_at=now,retain_until=now+7*86400,scope=SCOPES[env['template_id']],restore_verified=False,retry_of=op.get('recovery_point'),retirement_lock=oid if op['action']=='destroy' else None)
                    rows.append(fresh);op['recovery_point']=rid
                    for name in ['backup_job_id','backup_cursor','backup_verify_cursor']:op.pop(name,None)
                op['phase']=phase;op['status']='QUEUED';op['attempts']=0
                if automatic:op['automatic_retries']=op.get('automatic_retries',0)+1
                else:op['manual_retries']=op.get('manual_retries',0)+1
                op['generation']=op.get('generation',0)+1
                op['previous_error']=op.pop('error',None)
                # SSM commands are terminal after failure; issue a fresh command.
                for name in list(op):
                    if name.endswith('_command') or name.startswith(('app_command_','warehouse_','efs_bootstrap_','efs_ready_','efs_restore_copy_','efs_freeze_','efs_manifest_','efs_write_','efs_read_other_')):op.pop(name)
            if check_only:return {"allowed":True}
            self.store.commit(rows,expected(*rows));return self.store.get(op['pk'])
        return retry(commit)

    def backup_command(self, owner, rid, action, key, body):
        from .service import record, ident, retry, expected
        if body or action not in {'delete_backup','export_backup'}:
            raise HubError('INVALID_INPUT','Thao tác bản sao không hợp lệ.')
        def commit():
            rp=self.owned('R',rid,owner)
            ipk,fp,old=self.idempotency(owner,key,rid+'/'+action,{})
            if old:return self.owned('O',old['operation_id'],owner)
            if action=='delete_backup' and rp.get('retirement_lock'):
                raise HubError('RECOVERY_LOCKED','Bản sao cuối cùng được giữ đến khi xác nhận thu hồi sạch môi trường.',409)
            if rp.get('restore_lock') or rp.get('export_lock') or rp.get('delete_lock') or rp['status'] not in ({'AVAILABLE','DELETE_FAILED'} if action=='delete_backup' else {'AVAILABLE'}):
                raise HubError('RECOVERY_LOCKED','Bản sao đang được xử lý hoặc không sẵn sàng.',409)
            if action=='export_backup' and rp['retain_until']<=self.clock():
                raise HubError('RECOVERY_UNAVAILABLE','Bản sao đã hết hạn.',409)
            oid=ident('op-',ipk)
            op=record('operation',oid,owner,operation_id=oid,job_id=oid,environment_id=rp['environment_id'],
                action=action,status='QUEUED',phase='DELETE_BACKUP' if action=='delete_backup' else 'EXPORT_BACKUP',
                recovery_point=rid,region=self.region_for(rp),created_at=int(self.clock()),attempts=0,events=[])
            rp['delete_lock' if action=='delete_backup' else 'export_lock']=oid
            if action=='delete_backup':rp['status']='DELETING'
            rows=[rp,op,{'pk':ipk,'fingerprint':fp,'operation_id':oid}]
            self.store.commit(rows,expected(*rows));return self.store.get(op['pk'])
        return retry(commit)

    def cost_command(self, owner, eid, key, body):
        from .service import record, ident, retry, expected
        if body:raise HubError('INVALID_INPUT','Đối soát dùng nội dung rỗng.')
        def commit():
            env=self.owned('E',eid,owner)
            ipk,fp,old=self.idempotency(owner,key,eid+'/cost',{})
            if old:return self.owned('O',old['operation_id'],owner)
            if env.get('cost_lock') or self.clock()-env.get('cost_requested_at',-86400)<86400:
                raise HubError('COST_THROTTLED','Đối soát tối đa một lần mỗi 24 giờ cho mỗi môi trường.',409)
            oid=ident('op-',ipk)
            op=record('operation',oid,owner,operation_id=oid,job_id=oid,environment_id=eid,
                region=self.region_for(env),action='cost',status='QUEUED',phase='COST',created_at=int(self.clock()),attempts=0,events=[])
            env['cost_lock']=oid;env['cost_requested_at']=int(self.clock())
            rows=[env,op,{'pk':ipk,'fingerprint':fp,'operation_id':oid}]
            self.store.commit(rows,expected(*rows));return self.store.get(op['pk'])
        return retry(commit)

    def operation_actions(self,owner,oid):
        self.owned('O',oid,owner)
        result={}
        for action in ['retry','cancel']:
            try:
                self.control_operation(owner,oid,action,'eligibility-'+oid+'-'+action,{},check_only=True)
                result[action]={'allowed':True}
            except HubError as error:result[action]={'allowed':False,'reason_code':error.code}
        return result

    def environment_detail(self,owner,eid):
        from .catalog import SCOPES,environment_configuration
        env=self.owned('E',eid,owner)
        ops=sorted([o for o in self.store.list_owner(owner,'operation') if o.get('environment_id')==eid],key=lambda o:o.get('created_at',0),reverse=True)
        points=sorted([r for r in self.store.list_owner(owner,'recovery') if r.get('environment_id')==eid],key=lambda r:r.get('created_at',0),reverse=True)
        current=next((o for o in ops if o['operation_id']==env.get('lock')),ops[0] if ops else None)
        provision=next((o for o in ops if o.get('action') in {'create','restore'}),None)
        # Management jobs do not replace the provenance of infrastructure/data
        # readiness. A later file/app/backup operation cannot unverify a restore.
        readiness={'operation_id':provision.get('operation_id') if provision else None,
            'infrastructure_ready_at':env.get('ready_at') or (provision or {}).get('infrastructure_ready_at'),
            'data_verified_at':(provision or {}).get('data_verified_at'),
            'data_verification':(provision or {}).get('data_verification')}
        latest=points[0] if points else None
        pending=self.store.get('H#'+env['lock']) if str(env.get('lock','')).startswith('upload-') else None
        env['detail']={'readiness':readiness,'pending_upload':{k:pending.get(k) for k in ['upload_id','created_at','expires_at','complete_until','status']} if pending else None,'backup_scope':SCOPES[env['template_id']],
            'latest_backup':{k:latest.get(k) for k in ['recovery_point','status','created_at','completed_at','retain_until','scope','restore_verified']} if latest else None,
            'current_operation':{k:current.get(k) for k in ['operation_id','action','phase','status','created_at','updated_at','finished_at','infrastructure_ready_at','data_verified_at','data_verification']} if current else None,
            'actual_cost':env.get('cost_report',{'status':'NOT_AVAILABLE','actual_milliusd':None}),
            'restores_create_new_environment':True,'configuration':environment_configuration(env)}
        return env
