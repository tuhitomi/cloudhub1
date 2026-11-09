"""Prepare regional runtime/IAM documents from the reviewed control template.

Pure generation only: this module never calls AWS or enables a verification gate.
The caller must review costs, immutable regional IDs, IAM and cleanup before deploy.
"""
import json,re
from copy import deepcopy
from generate_network import generate as network_template

TARGETS={'ap-northeast-1','us-east-1'}

def chunks(statements,maximum=5700):
    result=[]; current=[]
    for statement in statements:
        if len(json.dumps({'Version':'2012-10-17','Statement':current+[statement]},separators=(',',':'))) > maximum:
            if not current:raise ValueError('A single IAM statement exceeds the policy limit')
            result.append(current);current=[]
        current.append(statement)
    if current:result.append(current)
    return [{'Version':'2012-10-17','Statement':items} for items in result]

def prepare(control,home,identities,region,ami_id):
    if region not in TARGETS or not re.fullmatch('ami-[a-f0-9]{8,17}',ami_id):raise ValueError('Invalid regional runtime location/image')
    account=home['account_id']; source=control['Resources']; role_name='cloudhub-runtime-'+region+'-cf'
    role_arn='arn:aws:iam::'+account+':role/'+role_name
    vault='cloudhub-region-'+region+'-data'
    backup_bucket='cloudhub-'+account+'-'+region+'-backup'
    boundary='arn:aws:iam::'+account+':policy/cloudhub-runtime-'+region+'-boundary'
    template=network_template();resources=template['Resources']
    resources['BackupVault']={'Type':'AWS::Backup::BackupVault','DeletionPolicy':'Retain','UpdateReplacePolicy':'Retain','Properties':{'BackupVaultName':vault}}
    resources['ImageRepository']={'Type':'AWS::ECR::Repository','DeletionPolicy':'Retain','UpdateReplacePolicy':'Retain','Properties':{
        'RepositoryName':'cloudhub-app','ImageTagMutability':'IMMUTABLE','EncryptionConfiguration':{'EncryptionType':'AES256'},
        'Tags':[{'Key':'cloudhub:managed','Value':'true'},{'Key':'cloudhub:purpose','Value':'regional-runtime'}]}}
    variable_map={
        'VpcId':{'Ref':'Vpc'},'PublicSubnetId':{'Ref':'Public1'},'PublicSubnet2Id':{'Ref':'Public2'},
        'DbSubnet1Id':{'Ref':'Db1'},'DbSubnet2Id':{'Ref':'Db2'},'AmiId':ami_id,
        'SessionRole.Arn':identities['SessionRole']['arn'],'SessionRole':identities['SessionRole']['name'],
        'SessionProfile':identities['SessionProfile'],'BackupRole.Arn':home['backup_role'],
        'BackupRestoreRole.Arn':home['backup_restore_role'],'Table.Arn':home['management_table_arn'],'Table':home['management_table'],
        'S3BackupBucket.Arn':'arn:aws:s3:::'+backup_bucket,'S3BackupBucket':backup_bucket,
        'BackupVault':vault,'BackupVault.BackupVaultArn':'arn:aws:backup:'+region+':'+account+':backup-vault:'+vault,
        'EnvironmentCfRole.Arn':role_arn,'EnvironmentBoundary':{'Ref':'EnvironmentBoundary'}}
    def transform(value,worker=False):
        variables={**variable_map}
        if worker:variables.update({'AWS::Region':region,'AWS::AccountId':account,'AWS::Partition':'aws','AWS::StackName':'cloudhub-pages-live','EnvironmentBoundary':boundary})
        if isinstance(value,list):return [transform(v,worker) for v in value]
        if not isinstance(value,dict):return value
        if set(value)=={'Ref'}:
            key=value['Ref']
            return deepcopy(variables.get(key,value))
        if set(value)=={'Fn::GetAtt'}:
            key=value['Fn::GetAtt'];key=key if isinstance(key,str) else '.'.join(key)
            return deepcopy(variables.get(key,value))
        if set(value)=={'Fn::Sub'}:
            original=value['Fn::Sub'];text=original if isinstance(original,str) else original[0]
            substitutions={} if isinstance(original,str) else {k:transform(v,worker) for k,v in original[1].items()}
            for name in re.findall(r'\$\{([^}]+)\}',text):
                if name.startswith('!') or name in substitutions:continue
                if name in variables:
                    entry=variables[name]
                    if isinstance(entry,str):text=text.replace('${'+name+'}',entry)
                    elif entry!={'Ref':name}:substitutions[name]=deepcopy(entry)
            if worker:
                # IAM policy JSON must have no unresolved CloudFormation references.
                if re.search(r'\$\{(?!aws:|!aws:)',text):raise ValueError('Unresolved worker policy variable: '+text)
                return text.replace('${!aws:','${aws:')
            if not substitutions and '${' not in text:return text
            if not substitutions and all(name.startswith('!') for name in re.findall(r'\$\{([^}]+)\}',text)):
                return text.replace('${!','${')
            return {'Fn::Sub':[text,substitutions]} if substitutions else {'Fn::Sub':text}
        return {key:transform(v,worker) for key,v in value.items()}
    def active(statement):
        actions=statement.get('Action',[]); actions=[actions] if isinstance(actions,str) else actions
        return not any(a.startswith(('redshift:','redshift-serverless:','redshift-data:')) for a in actions)
    def clean(statement):
        result=deepcopy(statement)
        # Preserve TagResource: real ApiGatewayV2 Stage creation requires it even
        # when older cfn-lint service metadata reports W3037 for this IAM verb.
        for values in result.get('Condition',{}).values():
            for key,value in list(values.items()):
                if isinstance(value,list):values[key]=[x for x in value if x not in {'redshift.amazonaws.com','redshift-serverless.amazonaws.com'}] if all(isinstance(x,str) for x in value) else value
        return result
    role=deepcopy(source['EnvironmentCfRole'])
    role['Properties']={k:v for k,v in role['Properties'].items() if k not in {'Policies','ManagedPolicyArns','RoleName'}}
    role['Properties']['RoleName']=role_name;resources['EnvironmentCfRole']=role
    original_boundary=source['EnvironmentBoundary']['Properties']['PolicyDocument']
    resources['EnvironmentBoundary']={'Type':'AWS::IAM::ManagedPolicy','Properties':{'ManagedPolicyName':'cloudhub-runtime-'+region+'-boundary',
        'PolicyDocument':transform(original_boundary)}}
    # The deployment role also has a boundary. Its exact reviewed policies below
    # still determine effective permissions; this ceiling cannot grant access.
    own_role='arn:aws:iam::'+account+':role/cloudhub-env-*'
    own_profile='arn:aws:iam::'+account+':instance-profile/cloudhub-env-*'
    ceiling=[{'Effect':'Allow','Action':[service+':*' for service in ['ec2','ssm','rds','secretsmanager','autoscaling','elasticloadbalancing','cloudwatch','elasticfilesystem','dynamodb','lambda','apigateway','logs','ecs']]+['kms:DescribeKey'],
        'Resource':'*','Condition':{'StringEquals':{'aws:RequestedRegion':region}}},
        {'Effect':'Allow','Action':'s3:*','Resource':['arn:aws:s3:::'+backup_bucket.removesuffix('backup')+'*','arn:aws:s3:::'+backup_bucket.removesuffix('backup')+'*/*']},
        {'Effect':'Allow','Action':'cloudfront:*','Resource':'*'},
        {'Effect':'Allow','Action':'iam:CreateRole','Resource':own_role,'Condition':{'ArnEquals':{'iam:PermissionsBoundary':{'Ref':'EnvironmentBoundary'}}}},
        {'Effect':'Allow','Action':['iam:DeleteRole','iam:GetRole','iam:PutRolePolicy','iam:GetRolePolicy','iam:DeleteRolePolicy','iam:ListRolePolicies','iam:TagRole','iam:UntagRole'],'Resource':own_role},
        {'Effect':'Allow','Action':['iam:CreateInstanceProfile','iam:DeleteInstanceProfile','iam:GetInstanceProfile','iam:AddRoleToInstanceProfile','iam:RemoveRoleFromInstanceProfile'],'Resource':own_profile},
        {'Effect':'Allow','Action':'iam:PassRole','Resource':[own_role,identities['SessionRole']['arn']],'Condition':{'StringEquals':{'iam:PassedToService':['ec2.amazonaws.com','lambda.amazonaws.com','ecs-tasks.amazonaws.com']}}},
        {'Effect':'Allow','Action':'iam:CreateServiceLinkedRole','Resource':'*','Condition':{'StringEquals':{'iam:AWSServiceName':['autoscaling.amazonaws.com','elasticloadbalancing.amazonaws.com','ecs.amazonaws.com','rds.amazonaws.com']}}}]
    resources['DeploymentBoundary']={'Type':'AWS::IAM::ManagedPolicy','Properties':{'ManagedPolicyName':'cloudhub-runtime-'+region+'-deployment-boundary','PolicyDocument':{'Version':'2012-10-17','Statement':ceiling}}}
    role['Properties']['PermissionsBoundary']={'Ref':'DeploymentBoundary'}
    statements=[]
    for name,row in source.items():
        if re.fullmatch(r'EnvironmentPolicy\d+',name) or name=='ProductContentPolicy':
            statements.extend(transform(clean(s)) for s in row['Properties']['PolicyDocument']['Statement'] if active(s))
    if not statements:raise ValueError('No reviewed environment policies found')
    for n,document in enumerate(chunks(statements)):
        resources['EnvironmentPolicy'+str(n)]={'Type':'AWS::IAM::ManagedPolicy','Properties':{'Roles':[{'Ref':'EnvironmentCfRole'}],'PolicyDocument':document}}
    workers=[]; api=[]
    def function_policies(name):
        rows=source[name]['Properties'].get('Policies')
        if rows is not None:return rows
        role=source[name+'Role']['Properties']
        return [p['PolicyDocument'] for p in role.get('Policies',[])]
    allowed={'cloudformation','ec2','ssm','backup','rds','autoscaling','elasticloadbalancing','cloudwatch','secretsmanager','elasticfilesystem','dynamodb','lambda','apigateway','logs','ecs'}
    for row in function_policies('WorkerFunction'):
        if not isinstance(row,dict):continue
        for statement in row.get('Statement',[]):
            actions=statement.get('Action',[]);actions=[actions] if isinstance(actions,str) else actions
            if not active(statement) or not actions or not all(a.split(':')[0] in allowed for a in actions):continue
            raw=json.dumps(statement)
            if 'Table' in raw and 'cloudhub-env-' not in raw:continue
            if '/cloudhub/' in raw:continue
            workers.append(transform(statement,True))
    workers.append({'Effect':'Allow','Action':'iam:PassRole','Resource':role_arn,'Condition':{'StringEquals':{'iam:PassedToService':'cloudformation.amazonaws.com'}}})
    # Existing IAM application reads and shared backup PassRole remain unchanged.
    for row in function_policies('ApiFunction'):
        if not isinstance(row,dict):continue
        for statement in row.get('Statement',[]):
            actions=statement.get('Action',[]);actions=[actions] if isinstance(actions,str) else actions
            if actions and all(a.startswith(('ec2:','ssm:')) for a in actions) and '/cloudhub/' not in json.dumps(statement):api.append(transform(statement,True))
    upload_scope='arn:aws:s3:::'+backup_bucket+'/uploads/env-*/upload-*'
    upload_permissions={'Effect':'Allow','Action':['s3:GetObject','s3:GetObjectVersion','s3:PutObject'],'Resource':upload_scope}
    workers.append(deepcopy(upload_permissions));api.append(deepcopy(upload_permissions))
    workers.append({'Effect':'Allow','Action':['cloudfront:GetDistributionConfig','cloudfront:UpdateDistribution'],'Resource':'arn:aws:cloudfront::'+account+':distribution/*','Condition':{'StringEquals':{'aws:ResourceTag/cloudhub:managed':'true'}}})
    workers.append({'Effect':'Allow','Action':'cloudfront:DescribeFunction','Resource':'arn:aws:cloudfront::'+account+':function/cloudhub-env-*-content'})
    # Existing retained backup buckets need a separately reviewed CORS/lifecycle update.
    # This generator does not adopt/create those buckets implicitly.
    template['Description']='CloudHub regional runtime: reviewed 2-AZ network, bounded deployment role, private DB subnets, backup vault and immutable image repository; no workload compute.'
    template['Outputs'].update({'CloudFormationRoleArn':{'Value':{'Fn::GetAtt':['EnvironmentCfRole','Arn']}},'BoundaryArn':{'Value':{'Ref':'EnvironmentBoundary'}},
        'BackupVaultName':{'Value':{'Ref':'BackupVault'}},'ImageRepositoryUri':{'Value':{'Fn::GetAtt':['ImageRepository','RepositoryUri']}}})
    return {'template':template,'worker_policies':chunks(workers),'api_policies':chunks(api),
        'settings':{'region':region,'prepared':True,'cf_role_arn':role_arn,'permissions_boundary':boundary,'backup_vault':vault,
            'backup_role':home['backup_role'],'backup_restore_role':home['backup_restore_role'],'s3_backup_bucket':backup_bucket,
            'instance_profile':home['instance_profile'],'ssh_cidr':home['ssh_cidr'],'ami_id':ami_id,'postgres_version':home['postgres_version']},
        'security_review':{'account':account,'region':region,'deployment_role':role_arn,'application_boundary':boundary,
            'worker_snapshot_delete':'native regional snapshot ARN, ec2:Owner account check, required owner/environment/recovery tags retained',
            'new_workload_gates_enabled':False,'t10_enabled':False,'new_runtime_resources':['2-AZ VPC/public and private DB subnets, IGW/routes','AWS Backup vault','immutable private ECR repository','bounded CloudFormation role and application permissions boundary']}}

def main():
    import argparse
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source-template','home-settings','identities','out'):
        parser.add_argument('--'+name,required=True,type=Path)
    parser.add_argument('--region',required=True,choices=sorted(TARGETS))
    parser.add_argument('--ami-id',required=True)
    args=parser.parse_args()
    read=lambda path:json.loads(path.read_text(encoding='utf-8'))
    result=prepare(read(args.source_template),read(args.home_settings),read(args.identities),args.region,args.ami_id)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('Prepared runtime/IAM documents only; no AWS calls or verification gates changed.')

if __name__=='__main__':main()
