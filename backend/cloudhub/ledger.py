"""Forecast ledger, never AWS billing/credits. Legacy amounts remain unreconciled."""
import hashlib
from decimal import Decimal
from .catalog import environment_configuration
from .errors import HubError


def normalize(row, now):
    if row.get('ledger_schema') != 2:
        row.update(ledger_schema=2, future_reserved_milliusd=0, accrued_estimate_milliusd=0,
                   legacy_unallocated_milliusd=int(row.get('reserved_milliusd', 0)),
                   released_estimate_milliusd=0, budget_cycle='PROJECT_LIFETIME',
                   ledger_migrated_at=now)
    return row


class LedgerMixin:
    def accounting_reservation(self, op, env, rows):
        """Join a reservation to the same operation/quota/quote transaction."""
        counter=next((r for r in rows if r['pk']=='Q#GLOBAL'),None)
        before=self.store.get('Q#GLOBAL') or {}
        amount=int(counter.get('reserved_milliusd',0))-int(before.get('reserved_milliusd',0)) if counter else 0
        if amount<=0:return []
        now=int(self.clock()); minutes=(env.get('operating_policy',{}).get('period_minutes') or env.get('estimate_hours',1)*60)
        if op['action']=='renew':minutes=op['minutes']
        reversible=0
        if op['action'] in {'create','restore','renew','resume_paused'}:
            # Only explicitly identified time-based lines can be released early.
            estimate=self.estimator_for(env).estimate(env['template_id'],Decimal(minutes)/60,renewal=True,backup=False,configuration=environment_configuration(env),workload=env.get('planning_workload'))
            timed={'storage','compute','root','data','ipv4','web_compute','web_root','web_ipv4','db_compute','db_storage',
                   'load_balancer','alb','container','task_ipv4','efs','warehouse','warehouse_storage'}
            reversible=min(amount,int(sum(Decimal(v) for k,v in estimate.get('lines',{}).items() if k in timed)*1200))
        rid=op['operation_id'];start=env.get('ready_at') if op['action']=='renew' else None
        if op['action']=='renew':start=max(op.get('previous_deadline',now),now)
        row={'pk':'F#'+rid,'kind':'reservation','owner_id':env['owner_id'],'owner_sort':'reservation#'+rid,
             'reservation_id':rid,'environment_id':env['environment_id'],'operation_id':rid,
             'region':self.region_for(env),'created_at':now,'amount_milliusd':amount,
             'run_milliusd':reversible,'allowance_milliusd':amount-reversible,'minutes':int(minutes),
             'start_at':start,'end_at':start+int(minutes)*60 if start is not None else None,
             'accrued_milliusd':0,'released_milliusd':0,'status':'RESERVED',
             'currency':'USD','budget_cycle':'PROJECT_LIFETIME',
             'allowance_reconciliation':'Unmeasured startup/request/log/backup envelope; not an actual charge or automatic refund'}
        if int(env.get('open_forecast_reservations',0))>=20:raise HubError('LEDGER_SETTLEMENT_REQUIRED','Settle pending forecast periods before accepting another charge.',409)
        env['open_forecast_reservations']=int(env.get('open_forecast_reservations',0))+1
        return [row]

    def settlement_rows(self, env, existing=()):
        """Settle observed elapsed forecast time; release only known unused run time."""
        now=int(self.clock()); updates=[];accrual=release=0
        final=env.get('paused_at') if env['status']=='PAUSED' else env.get('retired_at') if env['status']=='DELETED' else None
        reservations=[r for r in self.store.list_owner(env['owner_id'],'reservation') if r['environment_id']==env['environment_id'] and r['status'] not in {'SETTLED','RUN_SETTLED_ALLOWANCE_RETAINED','RECONCILIATION_REQUIRED'}]
        for candidate in reservations:
            r=self.store.get(candidate['pk'])
            if not r or r['status'] in {'SETTLED','RUN_SETTLED_ALLOWANCE_RETAINED','RECONCILIATION_REQUIRED'}:continue
            olda,oldr=int(r['accrued_milliusd']),int(r['released_milliusd'])
            if r['start_at'] is None:
                if env.get('ready_at') is not None and int(env['ready_at'])>=r['created_at'] and env['status'] in {'READY','PAUSED','DELETED'}:r['start_at']=int(env['ready_at']);r['end_at']=r['start_at']+r['minutes']*60
                elif env['status']=='DELETED':
                    # Failed creation can have incurred costs; do not manufacture a refund.
                    r['status']='RECONCILIATION_REQUIRED';updates.append(r);continue
                else:continue
            end=r['end_at']
            if final is not None and 'run_closed_at' not in r:r['run_closed_at']=int(final)
            closed=r.get('run_closed_at')
            observed=min(now,int(closed) if closed is not None else now)
            elapsed=max(0,min(observed,end)-r['start_at'])
            run=int(r['run_milliusd']);used=run*elapsed//max(1,end-r['start_at'])
            # Unmeasured request/startup/retention envelopes stay reserved for reconciliation.
            # Passage of seven days does not prove a backup was created or a cost incurred.
            allowance=0
            newa=max(olda,used+allowance)
            newr=max(oldr,run-used) if closed is not None and int(closed)<end else oldr
            if newa+newr>r['amount_milliusd']:raise HubError('LEDGER_INCONSISTENT','Forecast reservation requires reconciliation.',409)
            r.update(accrued_milliusd=newa,released_milliusd=newr,updated_at=now)
            if newa+newr==r['run_milliusd']:
                r['status']='RUN_SETTLED_ALLOWANCE_RETAINED' if r['allowance_milliusd'] else 'SETTLED';env['open_forecast_reservations']=max(0,int(env.get('open_forecast_reservations',0))-1)
            if newa!=olda or newr!=oldr:
                tag=hashlib.sha256((r['pk']+'|'+str(newa)+'|'+str(newr)).encode()).hexdigest()[:24]
                updates.append({'pk':'J#'+tag,'kind':'ledger_event','owner_id':env['owner_id'],
                    'owner_sort':'ledger_event#'+tag,'environment_id':env['environment_id'],
                    'reservation_id':r['reservation_id'],'created_at':now,'accrual_milliusd':newa-olda,
                    'release_milliusd':newr-oldr,'reason':'OBSERVED_PAUSE_RETIRE_OR_ELAPSED_FORECAST',
                    'is_aws_actual':False})
                accrual+=newa-olda;release+=newr-oldr
            updates.append(r)
        if not updates:return []
        for pk in ['Q#'+env['owner_id'],'Q#GLOBAL']:
            q=next((r for r in existing if r['pk']==pk),None) or self.store.get(pk) or {'pk':pk,'active':0,'reserved_milliusd':0}
            normalize(q,now)
            q['future_reserved_milliusd']-=accrual+release;q['accrued_estimate_milliusd']+=accrual
            q['released_estimate_milliusd']+=release;q['reserved_milliusd']-=release;q['ledger_updated_at']=now
            if q['future_reserved_milliusd']<0:raise HubError('LEDGER_INCONSISTENT','Reservation counters require reconciliation.',409)
            updates.append(q)
        return updates

    def settle_ledger(self,eid):
        from .service import expected,retry
        def transaction():
            env=self.store.get('E#'+eid)
            if not env:return
            rows=self.settlement_rows(env)
            if rows:
                rows.append(env);self.store.commit(rows,expected(*rows))
        return retry(transaction)

    def continuous_observation(self,eid):
        """Advisory only: no destructive action or recurring end schedule."""
        from .service import record,expected,retry
        from .operating_policy import current_policy
        def transaction():
            env=self.store.get('E#'+eid)
            if not env or current_policy(env)['mode']!='CONTINUOUS' or env['status'] not in {'READY','BACKING_UP'}:return
            now=int(self.clock());elapsed=max(1,(now-int(env.get('continuous_segment_start_at',env.get('ready_at',now)))+3599)//3600)
            estimate=self.estimator_for(env).estimate(env['template_id'],elapsed,renewal=True,backup=False,configuration=environment_configuration(env),workload=env.get('planning_workload'))
            quota=self.store.get('Q#'+env['owner_id']) or {}
            threshold=min(current_policy(env).get('budget_limit_milliusd') or self.budget,int(quota.get('budget_milliusd',self.budget)),self.budget)
            previous=int(env.get('continuous_unreserved_observed_milliusd',0))
            preview=env.get('continuous_segment_reserved_milliusd',env.get('cost_plan',{}).get('first_period',{}).get('total_milliusd',0)) or 0
            base=int(env.get('continuous_segment_base_milliusd',0))
            observed=max(previous,base+max(0,int(estimate.get('total_milliusd') or 0)-int(preview)))
            cumulative=self._committed(env)+observed
            extra=[]
            if observed>previous:
                for pk in ['Q#'+env['owner_id'],'Q#GLOBAL']:
                    q=self.store.get(pk) or {'pk':pk,'active':0,'reserved_milliusd':0};normalize(q,now)
                    q['observed_unreserved_milliusd']=int(q.get('observed_unreserved_milliusd',0))+observed-previous
                    q['ledger_updated_at']=now;extra.append(q)
                event=record('ledger_event','continuous-'+eid+'-'+str(observed),env['owner_id'],environment_id=eid,
                    created_at=now,unreserved_forecast_milliusd=observed-previous,is_aws_actual=False)
                extra.append(event);env['continuous_unreserved_observed_milliusd']=observed
            env['continuous_cost_observation']={'checked_at':now,'elapsed_hours':elapsed,
                'estimated_milliusd':cumulative if estimate.get('approved') else None,'status':'ESTIMATED' if estimate.get('approved') else 'PRICES_UNAVAILABLE','last_known_committed_milliusd':cumulative,'segment_estimated_milliusd':estimate.get('total_milliusd'),'is_aws_actual':False,
                'threshold_milliusd':threshold,'action':'ALERT_ONLY_PRESERVE_SOURCE',
                'beyond_reserved_preview':observed>base}
            rows=[env,*extra]
            if not estimate.get('approved'):
                nid='continuous-prices-'+eid
                if not self.store.get('N#'+nid):rows.append(record('notification',nid,env['owner_id'],notification_id=nid,environment_id=eid,type='CONTINUOUS_COST_UNAVAILABLE',message_key='continuous.pricesUnavailable',created_at=now))
            if estimate.get('total_milliusd') is not None and cumulative>=threshold:
                nid='continuous-budget-'+eid
                if not self.store.get('N#'+nid):
                    rows.append(record('notification',nid,env['owner_id'],notification_id=nid,
                        environment_id=eid,type='CONTINUOUS_BUDGET_WARNING',message_key='continuous.budgetWarning',
                        created_at=now,message='Forecast threshold reached. Resources and source data are preserved.'))
            self.store.commit(rows,expected(*rows))
        return retry(transaction)

    def emit_continuous_notices(self,eid,emit):
        """Durable advisory outbox to existing CloudWatch/SNS, at least once.

        Log first, acknowledge only after emission. A crash can duplicate the
        advisory metric; it can never end an environment or lose the N# record.
        """
        env=self.store.get('E#'+eid)
        if not env:return
        for item in self.store.list_owner(env['owner_id'],'notification'):
            if item.get('environment_id')!=eid or item.get('type') not in {'CONTINUOUS_BUDGET_WARNING','CONTINUOUS_COST_UNAVAILABLE'}:continue
            row=self.store.get(item['pk'])
            if not row or row.get('operational_log_emitted_at') is not None:continue
            emit({'event':'CloudHubContinuousWarning','notification_id':row['notification_id'],
                'environment_id':eid,'owner_id':env['owner_id'],'type':row['type'],
                'action':'ALERT_ONLY_PRESERVE_SOURCE','source_preserved':True})
            row['operational_log_emitted_at']=int(self.clock())
            self.save(row)
