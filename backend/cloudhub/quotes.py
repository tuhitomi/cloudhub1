"""Owner-bound, single-use estimates. Quote consumption joins the command transaction."""
import hashlib
import json
import uuid
from decimal import Decimal
from .errors import HubError


def fingerprint(value):
    def number(v):
        if isinstance(v, Decimal):
            return int(v) if v == v.to_integral_value() else str(v)
        raise TypeError(type(v).__name__)
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), default=number).encode()).hexdigest()


def quote_error(code):
    return HubError(code, 'The estimate must be reviewed and confirmed again.', 409,
                    details={'review_required': True, 'retryable_with_same_quote': False})


class QuoteMixin:
    def termination_terms(self, env, action):
        """Data consent is independent of price availability and spending headroom."""
        from .operating_policy import current_policy
        from .catalog import SCOPES
        ending = 'BACKUP_RETIRE' if action == 'destroy' else current_policy(env)['ending_policy']
        return {'action': action, 'environment_id': env['environment_id'], 'region': self.region_for(env),
                'revision': int(env.get('lifecycle_revision', 0)), 'configuration': env.get('configuration'),
                'status': env['status'], 'ending_policy': ending, 'retention_days': 7 if ending == 'BACKUP_RETIRE' else None,
                'scope': SCOPES[env['template_id']], 'mandatory_backup': ending == 'BACKUP_RETIRE',
                'cost_policy': 'REDUCE_RUNNING_COST_PRESERVE_SOURCE',
                'additional_retention_cost_acknowledged': True}

    def termination_review(self, owner, env, action):
        now=int(self.clock());terms=self.termination_terms(env,action);qid='quote-'+uuid.uuid4().hex
        row={'pk':'V#'+qid,'kind':'termination_consent','owner_id':owner,'owner_sort':'termination_consent#'+qid,
             'quote_id':qid,'created_at':now,'expires_at':now+120,'ttl':now+86400,
             'terms':terms,'fingerprint':fingerprint(terms),'consumed_by':None}
        self.store.commit([row],{row['pk']:None})
        return {'approved':True,'review_kind':'TERMINATION_DATA_CONSENT','quote_id':qid,
                'quote_expires_at':now+120,'currency':'USD','terms':terms,
                'additional_commitment_milliusd':None,'cumulative_after_milliusd':None,
                'after_shutdown':{'total_milliusd':None,'period_hours':168 if terms['mandatory_backup'] else 24},
                'budget_is_aws_billing_cap':False,'price_approval':False,
                'unknown':['Termination does not require a spending reservation. Backup processing, retained data, logs and paused storage may incur additional charges; their current price is not confirmed here. The selected data policy remains mandatory.']}

    def consume_termination(self, owner, env, action, body, oid):
        if not self.require_quotes and not body.get('quote_id'):return []
        if body.get('confirmed') is not True or body.get('expected_revision') != int(env.get('lifecycle_revision',0)) or type(body.get('expected_revision')) is not int:
            raise HubError('POLICY_CONSENT_REQUIRED','Review the current data policy and revision before ending this environment.',409)
        row=self.store.get('V#'+str(body.get('quote_id','')))
        if not row or row.get('owner_id')!=owner:raise HubError('NOT_FOUND','Termination review not found.',404)
        if row.get('kind')!='termination_consent':raise quote_error('QUOTE_CHANGED')
        if row.get('consumed_by'):raise quote_error('QUOTE_CONSUMED')
        if int(row['expires_at'])<=int(self.clock()):raise quote_error('QUOTE_EXPIRED')
        if row['fingerprint']!=fingerprint(self.termination_terms(env,action)):raise quote_error('QUOTE_CHANGED')
        row.update(consumed_by=oid,consumed_at=int(self.clock()))
        return [row]

    def issue_quote(self, owner, action, inputs, estimate, environment=None):
        now = int(self.clock())
        qid = 'quote-' + uuid.uuid4().hex
        terms = self.quote_terms(action, inputs, estimate, environment)
        row = {'pk': 'V#' + qid, 'kind': 'quote', 'owner_id': owner,
               'owner_sort': 'quote#' + qid, 'quote_id': qid, 'action': action,
               'created_at': now, 'expires_at': now + 120, 'ttl': now + 86400,
               'terms': terms, 'fingerprint': fingerprint(terms), 'consumed_by': None}
        self.store.commit([row], {row['pk']: None})
        return {**estimate, 'quote_id': qid, 'quote_created_at': now,
                'quote_expires_at': row['expires_at'], 'quote_fingerprint': row['fingerprint'],
                'price_version': terms['price_version'], 'currency': 'USD'}

    def quote_terms(self, action, inputs, estimate, environment=None):
        region = estimate.get('region') or (self.region_for(environment) if environment else self.region_registry().select(inputs.get('region')))
        # Includes all selected pricing assumptions, not just total/updated_at.
        prices = self.estimator_for(region).rates
        terms = {'action': action, 'inputs': inputs, 'estimate': estimate,
                 'price_version': fingerprint(prices), 'region': region, 'currency': 'USD'}
        if environment:
            terms['environment'] = {k: environment.get(k) for k in
                ['environment_id', 'template_id', 'configuration', 'lifecycle_revision', 'deadline',
                 'operating_policy', 'estimated_committed_milliusd', 'status']}
        return terms

    def consume_quote(self, owner, qid, action, inputs, estimate, operation_id, environment=None):
        if not self.require_quotes and not qid:
            return []  # Explicit trusted local/legacy harness only; runtime always enforces quotes.
        if estimate.get('approved') is not True:raise quote_error('QUOTE_UNAPPROVED')
        if not isinstance(qid, str) or not qid.startswith('quote-'):
            raise quote_error('QUOTE_REQUIRED')
        row = self.store.get('V#' + qid)
        if not row or row.get('owner_id') != owner:
            raise HubError('NOT_FOUND', 'Estimate not found.', 404)
        if row.get('consumed_by'):
            raise quote_error('QUOTE_CONSUMED')
        if int(row['expires_at']) <= int(self.clock()):
            raise quote_error('QUOTE_EXPIRED')
        terms = self.quote_terms(action, inputs, estimate, environment)
        if row['fingerprint'] != fingerprint(terms):
            raise quote_error('QUOTE_CHANGED')
        row.update(consumed_by=operation_id, consumed_at=int(self.clock()))
        return [row]

    def create_estimate(self, owner, body, is_admin=False):
        inputs = {k: v for k, v in body.items() if k != 'quote_id'}
        if inputs.get('recovery_point'):
            from .applications import restore_inputs
            inputs=restore_inputs(self,owner,inputs)
            source = self.owned('R', inputs['recovery_point'], owner)
            inputs = {**inputs, 'configuration': inputs.get('configuration', source.get('configuration')),
                      'region': inputs.get('region', self.region_for(source))}
        _, _, _, estimate = self.validate_create(inputs, is_admin)
        estimate = {**estimate, 'configuration_verified': True, 'budget_feasible': True}
        return self.issue_quote(owner, 'restore' if inputs.get('recovery_point') else 'create', self.create_quote_inputs(inputs, estimate), estimate)

    def create_quote_inputs(self,body,estimate):
        source=self.store.get('R#'+body['recovery_point']) if body.get('recovery_point') else None
        source_snapshot={k:source.get(k) for k in ['created_at','retain_until','manifest_sha256','scope','configuration','region','status']} if source else None
        return {'template_id': body['template_id'], 'region': estimate['region'],
                'configuration': estimate['configuration'], 'operating_policy': estimate['operating_policy'],
                'estimate_hours': estimate['estimate_hours'], 'recovery_point': body.get('recovery_point'),
                **({'planning_workload':estimate['planning_workload']} if estimate.get('planning_workload') is not None else {}),
                **({'application':estimate['application']} if estimate.get('application') else {}),
                'validation_run': body.get('validation_run', False), 'retention_days': 7,'recovery_source':source_snapshot}
