import json
import os
import time
from copy import deepcopy
from .cost import Estimator
from .service import Service
from .store import DynamoStore
from .driver_router import DriverRouter

def build_service():
    region_config=region_configuration()
    return Service(DynamoStore(os.environ["TABLE_NAME"]), estimator=Estimator(regional_prices()),
        verified=filter(None, os.getenv("VERIFIED_TEMPLATES", "").split(",")),
        validation=filter(None, os.getenv("VALIDATION_TEMPLATES", "").split(",")),
        user_limit=int(os.getenv("USER_LIMIT", "2")), total_limit=int(os.getenv("TOTAL_LIMIT", "4")),
        budget_milliusd=int(os.environ["BUDGET_MILLIUSD"]),workflow_terminal=workflow_terminal,
        price_provider=lambda:regional_prices(force=True),
        catalog_price_provider=regional_prices,
        regions_config=region_config,regions_provider=region_configuration,
        continuous_enabled=os.getenv('CONTINUOUS_ENABLED','false').lower()=='true',
        recommendations_enabled=os.getenv('RECOMMENDATIONS_ENABLED','false').lower()=='true',
        direct_upload_enabled=os.getenv('DIRECT_UPLOAD_ENABLED','false').lower()=='true')

def region_configuration():
    value=configuration_document('REGIONS_PARAMETER','REGIONS_JSON')
    home=os.environ.get('AWS_REGION','ap-southeast-1')
    if value.get('pricing_unavailable'):
        return {'control_region':home,'regions':{r:{'enabled':False,'prepared':False} for r in ('ap-southeast-1','ap-northeast-1','us-east-1')}}
    if value.get('control_region',home)!=home:
        raise ValueError('Control Region does not match this Lambda deployment')
    value=deepcopy(value)
    # One Standard parameter per Region keeps all 18 configuration proofs below
    # 4 KiB. A missing shard closes only its Region; never use stale inline proof.
    from .regions import REGIONS
    import re
    for region,policy in value.get('regions',{}).items():
        path=policy.get('verifications_parameter')
        if not path:continue
        policy['verifications']={}
        if region not in REGIONS or not isinstance(path,str) or not re.fullmatch(
                r'/cloudhub/[A-Za-z0-9_-]+/regions/verifications/'+re.escape(region),path):
            policy['enabled']=False
            continue
        shard=load_prices(path)
        if shard.get('pricing_unavailable') or shard.get('region')!=region or shard.get('schema')!=1 or not isinstance(shard.get('verifications'),dict):
            policy['enabled']=False
            continue
        policy['verifications']=shard['verifications']
    return {**value,'control_region':home}

def configuration_document(parameter_key,json_key):
    name=os.getenv(parameter_key)
    return load_prices(name) if name else json.loads(os.getenv(json_key,'{}'))

def regional_prices(force=False):
    read=(lambda name:load_prices(name,force=True)) if force else load_prices
    rates=dict(read(os.getenv('PRICES_PARAMETER')))
    parameters=json.loads(os.getenv('REGIONAL_PRICES_PARAMETERS_JSON','{}'))
    rates['regional_rates']={region:read(name) for region,name in parameters.items()}
    if os.getenv('CLOUDFRONT_VIEWER_PRICES_PARAMETER'):
        from .viewer_prices import apply
        viewers=read(os.environ['CLOUDFRONT_VIEWER_PRICES_PARAMETER'])
        rates=apply(rates,viewers)
        rates['regional_rates']={region:apply(value,viewers) for region,value in rates['regional_rates'].items()}
    return rates

_PRICE_CACHE={}
_PARAMETER_CLIENT=None

def parameter_client():
    """Reuse the regional SDK connection pool, never bypass a fresh price read."""
    global _PARAMETER_CLIENT
    if _PARAMETER_CLIENT is None:
        import boto3
        from botocore.config import Config
        _PARAMETER_CLIENT=boto3.client('ssm',config=Config(connect_timeout=.4,read_timeout=.7,retries={'total_max_attempts':1}))
    return _PARAMETER_CLIENT
def load_prices(parameter_name,force=False):
    if not parameter_name:return json.loads(os.environ['PRICES_JSON'])
    cached=_PRICE_CACHE.get(parameter_name)
    if not force and cached and time.monotonic()-cached['at']<60:return cached['rates']
    client=parameter_client()
    try:rates=json.loads(client.get_parameter(Name=parameter_name,WithDecryption=False)['Parameter']['Value'])
    except Exception:
        return {**(cached['rates'] if cached else {}),'approved':False,'pricing_unavailable':True}
    _PRICE_CACHE[parameter_name]={'at':time.monotonic(),'rates':rates};return rates

def driver_settings():
    settings=configuration_document('DRIVER_SETTINGS_PARAMETER','DRIVER_SETTINGS')
    if settings.get('pricing_unavailable') or not settings.get('region'):
        from .errors import HubError
        raise HubError('REGION_NOT_PREPARED','Infrastructure settings cannot be read; source data is preserved.',409)
    settings['regions']=configuration_document('DRIVER_REGIONS_PARAMETER','DRIVER_REGIONS_JSON')
    settings['control_region']=settings['region']
    return settings

def build_driver():
    return DriverRouter(driver_settings())

def enqueue_dispatch(oid):
    """Queue on the existing expiry Lambda; sweeper is the durable outbox fallback."""
    import boto3
    from botocore.config import Config
    return boto3.client("lambda",config=Config(connect_timeout=.4,read_timeout=.7,retries={"total_max_attempts":1})).invoke(
        FunctionName=os.environ["ASYNC_DISPATCH_FUNCTION"],InvocationType="Event",
        Payload=json.dumps({"kind":"DISPATCH_OPERATION","operation_id":oid}).encode())


def dispatch(oid):
    import boto3
    from botocore.config import Config
    from botocore.exceptions import ClientError
    client = boto3.client("stepfunctions", config=Config(connect_timeout=0.4, read_timeout=0.7, retries={"total_max_attempts": 1}))
    try:
        service=build_service()
        op=service.store.get('O#'+oid)
        return client.start_execution(stateMachineArn=os.environ["STATE_MACHINE_ARN"], name=execution_name(op),
            input=json.dumps({"operation_id": oid,'generation':int(op.get('generation',0)),'region':service.region_for(op)}, separators=(",", ":")))
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ExecutionAlreadyExists":
            raise

def execution_name(op):
    return op['operation_id']+('-r'+str(op['generation']) if op.get('generation') else '')

def workflow_terminal(op):
    import boto3
    from botocore.exceptions import ClientError
    arn=os.environ['STATE_MACHINE_ARN'].replace(':stateMachine:',':execution:')+':'+execution_name(op)
    try:return boto3.client('stepfunctions').describe_execution(executionArn=arn)['status'] in {'SUCCEEDED','FAILED','TIMED_OUT','ABORTED'}
    except ClientError as exc:
        if exc.response['Error']['Code']=='ExecutionDoesNotExist':return True
        raise

def expiry_handler(event, context=None):
    if event.get("kind")=="DISPATCH_OPERATION":
        dispatch(event["operation_id"]);return {"accepted":True}
    service = build_service()
    if event.get('region'):
        env=service.store.get('E#'+event['environment_id'])
        if not env or service.region_for(env)!=event['region']:return {'accepted':False}
    if 'expected_deadline' not in event or 'expected_revision' not in event:
        from .operating_policy import revision
        env=service.store.get('E#'+event['environment_id'])
        # Legacy callbacks cannot identify their old deadline. Once management has
        # changed the revision, only the new fenced schedule (or fresh sweep) acts.
        if not env or revision(env)>0:return {'accepted':False}
    op = service.expire(event["environment_id"],event.get('expected_deadline'),event.get('expected_revision'))
    if op:
        dispatch(op["operation_id"])
    return {"accepted": bool(op)}

def sweep_handler(event, context=None):
    service, driver = build_service(), build_driver()
    errors = []
    for env in service.store.scan_kind("environment"):
        try:
            from .uploads import expire_upload
            expire_upload(service,env['environment_id'])
            service.settle_ledger(env['environment_id'])
            service.continuous_observation(env['environment_id'])
            service.emit_continuous_notices(env['environment_id'],lambda item:print(json.dumps(item)))
            service.remind(env['environment_id'])
            env=service.store.get(env['pk'])
            if env["status"] == "READY" and env.get("deadline") is not None and env["deadline"] <= service.clock():
                op = service.expire(env["environment_id"])
                if op:
                    dispatch(op["operation_id"])
            elif env.get('schedule_pending') and not env.get('lock'):
                repair=service.enqueue_schedule_repair(env['environment_id'])
                if repair:dispatch(repair['operation_id'])
            # Scheduler repair is a durable operation holding the environment lock.
            # Never perform an unfenced read/SDK/update sequence from the sweeper.
        except Exception as exc:
            errors.append({"environment_id": env["environment_id"], "error": type(exc).__name__})
    for op in service.store.scan_kind("operation"):
        try:
            recovered=service.retry_automatic_operation(op)
            if recovered:
                dispatch(recovered['operation_id']);continue
            if op["status"] == "QUEUED":
                dispatch(op["operation_id"])
            if op["status"] in {"QUEUED", "RUNNING"}:
                import boto3
                execution_arn = os.environ["STATE_MACHINE_ARN"].replace(":stateMachine:", ":execution:") + ":" + execution_name(op)
                result = boto3.client("stepfunctions").describe_execution(executionArn=execution_arn)
                if result["status"] in {"FAILED", "TIMED_OUT", "ABORTED", "SUCCEEDED"}:
                    current = service.store.get(op["pk"])
                    if current["status"] in {"QUEUED", "RUNNING"}:
                        from .worker import Worker
                        Worker(service, driver).fail(op["operation_id"], "WORKFLOW_" + result["status"],op.get('generation',0))
        except Exception as exc:
            errors.append({"operation_id": op["operation_id"], "error": type(exc).__name__})
    for rp in service.store.scan_kind("recovery"):
        try:
            expirable = {'AVAILABLE','EXPIRING','FAILED','DELETE_FAILED'}
            if rp["status"] in expirable and rp["retain_until"] <= service.clock() and not (rp.get("restore_lock") or rp.get('export_lock') or rp.get('delete_lock') or rp.get('retirement_lock')):
                # Fence restore against retention expiry before touching AWS.
                rp["status"] = "EXPIRING"
                rp['region']=service.region_for(rp)
                service.save(rp)
                rp = service.store.get(rp['pk'])
                deleted = driver.expire_backup(rp)
                if deleted:
                    rp["status"] = "EXPIRED"
                service.save(rp)
        except Exception as exc:
            errors.append({"recovery_point": rp["recovery_point"], "error": type(exc).__name__})
    try:
        from .announcements import Announcements,runtime_writer
        writer=runtime_writer()
        if writer is not None:
            announcements=Announcements(service)
            result=announcements.sync_public(writer)
            queued=announcements.queue_emails(limit=10)
            if result or queued:print(json.dumps({'event':'CloudHubMaintenanceDispatch','public_sync':result,'queued':queued}))
    except Exception as exc:
        errors.append({'notification_channel':'maintenance-public','error':type(exc).__name__})
    try:
        from .notification_email import runtime_gateway
        gateway=runtime_gateway()
        if gateway is not None:
            from .notifications import NotificationCenter
            from .accounts import Accounts
            accounts=Accounts(os.environ['USER_POOL_ID'])
            outcomes=NotificationCenter(service).drain(gateway,accounts.identity,limit=10)
            print(json.dumps({'event':'CloudHubUserNotificationDispatch','items':outcomes}))
    except Exception as exc:
        # Report the channel failure without hiding earlier lifecycle errors or
        # logging an address, a confirmation URL, or a provider response body.
        errors.append({'notification_channel':'user-email','error':type(exc).__name__})
    if errors:
        print(json.dumps({"event": "CloudHubSweepFailed", "errors": errors}))
        raise RuntimeError("Sweep incomplete; failed items will be retried")
    return {"status": "ok"}
