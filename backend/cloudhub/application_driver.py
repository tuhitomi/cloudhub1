"""One bounded step per invocation; deploy reviewed bytes, never client code.

The CloudFormation bootstrap is updated first so future T04 nodes cannot start
an old version. Partial/unknown outcomes stay pending or fail for reconciliation.
"""
import base64,json,hashlib
from pathlib import Path
from .errors import HubError

def node_script(app,oid):
    from .applications import configuration_json
    files={'content_app.py':Path(__file__).with_name('content_app.py').read_bytes(),'app.py':Path(__file__).with_name('rds_app.py').read_bytes(),
        'application.json':configuration_json(app).encode()}
    digest=hashlib.sha256(b''.join(files[k] for k in sorted(files))).hexdigest()
    # Text/config are base64 data. Only fixed paths and generated operation IDs
    # reach the shell. Markers make an uncertain SSM retry idempotent.
    script='set -eu\ncd /opt/cloudhub\nmkdir -p application-operations\nexec 9>application-operations/deploy.lock\nflock -x -w 30 9\n'
    script+=f"if test -f application-operations/{oid}; then test \"$(cat application-operations/{oid})\" = '{digest}'; curl --fail --silent --max-time 5 http://127.0.0.1:8080/health; exit 0; fi\n"
    script+="before=$(curl --fail --silent --max-time 5 http://127.0.0.1:8080/internal/manifest)\nmkdir -p application-rollback\n"
    for name,body in files.items():
        encoded=base64.b64encode(body).decode();sha=hashlib.sha256(body).hexdigest()
        script+=f"cp {name} application-rollback/{name}\nprintf '%s' '{encoded}' | base64 --decode > {name}.pending\nprintf '%s  %s\\n' '{sha}' '{name}.pending' | sha256sum --check --status\n"
    script+='chmod 600 application.json.pending\n'
    for name in files:script+=f'mv {name}.pending {name}\n'
    script+="systemctl restart cloudhub-app\nok=0\nfor step in $(seq 1 15); do if curl --fail --silent --max-time 1 http://127.0.0.1:8080/health > application-health.json; then ok=1; break; fi; sleep 1; done\n"
    script+=f"if test \"$ok\" = 1; then /opt/cloudhub/venv/bin/python -c 'import json; assert json.load(open(\"application-health.json\"))[\"application_revision\"]==\"{app['revision']}\"' || ok=0; fi\n"
    script+='if test "$ok" = 1; then after=$(curl --fail --silent --max-time 5 http://127.0.0.1:8080/internal/manifest); test "$before" = "$after" || ok=0; fi\n'
    script+='if test "$ok" != 1; then cp application-rollback/* .; systemctl restart cloudhub-app; exit 1; fi\n'
    script+=f"printf '%s' '{digest}' > application-operations/{oid}\ncat application-health.json\n"
    return script

def deploy(driver,env,op,before_mutation=lambda:None):
    target=op['application_target'];stage=op['application_step'];stack=driver.assert_stack(env)
    if not stack:raise HubError('APPLICATION_DEPLOY_FAILED','Owned stack missing; source metadata is preserved.',409)
    if stage in {'UPDATE_BOOTSTRAP','WAIT_BOOTSTRAP'}:
        from .applications import deployment_parameters
        desired=deployment_parameters(target);present={p['ParameterKey']:p.get('ParameterValue') for p in stack.get('Parameters',[])}
        if not desired.keys()<=present.keys():raise HubError('APPLICATION_LEGACY_MIGRATION_REQUIRED','This stack has no reviewed parameter contract; an operator must review a separate migration.',409)
        if any(present.get(k)!=v for k,v in desired.items()):
            if stack['StackStatus'].endswith('_IN_PROGRESS'):return False
            if stage=='WAIT_BOOTSTRAP' and op.get('bootstrap_accepted'):raise HubError('APPLICATION_RECONCILE_REQUIRED','Bootstrap does not match the accepted release; reconcile before retry.',409)
            op['application_step']='WAIT_BOOTSTRAP';before_mutation()
            parameters=[{'ParameterKey':k,'ParameterValue':desired[k]} if k in desired else {'ParameterKey':k,'UsePreviousValue':True} for k in present]
            driver.cloudformation.update_stack(StackName=driver.stack_name(env),UsePreviousTemplate=True,Parameters=parameters,Capabilities=['CAPABILITY_NAMED_IAM'],DisableRollback=True,
                RoleARN=driver.settings['cf_role_arn'],ClientRequestToken=op['operation_id']+'-app-g'+str(op.get('generation',0)))
            op['bootstrap_accepted']=True;return False
        if stack['StackStatus'].endswith('_IN_PROGRESS'):return False
        if stack['StackStatus'] not in {'CREATE_COMPLETE','UPDATE_COMPLETE'}:raise HubError('APPLICATION_RECONCILE_REQUIRED','Bootstrap update is not complete; preserve database and inspect the operation.',409)
        # A T03 UserData update can restart EC2 and change its public IPv4.
        # Publish the current CFN outputs rather than retaining a stale address.
        if stack.get('Outputs'):
            env['outputs']={v['OutputKey']:v['OutputValue'] for v in stack['Outputs']};driver.apply_outputs(env)
        op['application_step']='APPLY_NODES';op.setdefault('application_nodes',{});return False
    instances=driver.active_instances(env)
    if not instances or len(instances)>2:raise HubError('APPLICATION_RECONCILE_REQUIRED','Expected one or two owned application nodes.',409)
    done=op.setdefault('application_nodes',{})
    for node in instances:
        iid=node['InstanceId']
        if done.get(iid):continue
        env['instance_id']=iid;field='app_command_'+iid;before_mutation()
        result=driver.command(env,op,node_script(target,op['operation_id']),field)
        if result is None:return False
        health=json.loads(result)
        if health.get('application_revision')!=target['revision']:raise HubError('APPLICATION_RECONCILE_REQUIRED','Node returned an unexpected release.',409)
        done[iid]=True;return False
    # Re-evaluate the current ASG inventory on every tick. A newly started node
    # must be checked too, rather than assuming all nodes switch simultaneously.
    return all(done.get(node['InstanceId']) for node in instances)
