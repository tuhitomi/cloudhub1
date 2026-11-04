"""F02: immutable approved configurations; validation gate is server-side."""
import os
import hashlib
import json
from decimal import Decimal
from .errors import HubError

NAMES = [
    ("T01", "Máy Linux", "Học Linux và chạy công cụ", ["EC2", "EBS"]),
    ("T02", "Website tĩnh", "Đăng website HTML", ["S3", "CloudFront"]),
    ("T03", "Web và cơ sở dữ liệu", "Ứng dụng có dữ liệu", ["EC2", "RDS"]),
    ("T04", "Web cân bằng tải", "Phân phối tải giữa các máy ứng dụng", ["ALB", "Auto Scaling", "RDS"]),
    ("T05", "Website trên máy chủ", "Website trên Linux", ["EC2", "web server"]),
    ("T06", "Ứng dụng Docker", "Chạy image được duyệt", ["ECS Fargate"]),
    ("T07", "Kho file và chia sẻ", "Chia sẻ file có thời hạn", ["S3"]),
    ("T08", "Ổ đĩa dùng chung", "Chia sẻ dữ liệu hai máy", ["EFS", "EC2"]),
    ("T09", "API serverless", "API và dữ liệu theo yêu cầu", ["API Gateway", "Lambda", "DynamoDB"]),
    ("T10", "Kho dữ liệu phân tích", "Phân tích dữ liệu mẫu", ["Redshift Serverless", "S3"]),
]
IMPLEMENTED = {'T01','T02','T03','T04','T05','T06','T07','T08','T09','T10'}
# Keep legacy processors/configuration readable; T10 is outside the current product scope.
ACTIVE_TEMPLATES = IMPLEMENTED - {'T10'}
S3_CONFIG = {"max_files": 32, "max_file_bytes": 8192, "max_total_bytes": 262144, "max_writes": 128}
SCOPES={
    'T01':'EBS /data sau dừng máy; không gồm root, RAM hoặc dữ liệu ngoài /data',
    'T05':'EBS /data và nội dung web trong /data; không gồm root/RAM',
    'T02':'File S3 hiện hành, checksum SHA-256; không gồm lịch sử phiên bản hay cấu hình CloudFront',
    'T07':'File S3 hiện hành, checksum SHA-256; không giữ hiệu lực liên kết chia sẻ cũ',
    'T03':'PostgreSQL: snapshot RDS và checksum bản ghi minh họa; không gồm root EC2',
    'T04':'PostgreSQL: snapshot RDS và checksum; ALB/ASG/EC2 được dựng mới',
    'T06':'S3 được đăng ký làm dữ liệu bền vững; không gồm filesystem tạm của container, RAM hay image',
    'T08':'EFS sau khóa ghi cả hai máy; checksum /records; không gồm root EC2',
    'T09':'Bản ghi người dùng DynamoDB, đọc nhất quán và SHA-256; không gồm nhật ký idempotency của môi trường cũ',
    'T10':'Snapshot namespace Redshift và file S3 hiện hành; checksum dữ liệu truy vấn, không gồm kết quả truy vấn tạm'
}

def configuration(code):
    if code in {'T02','T07'}:return S3_CONFIG.copy()
    if code in {'T01','T05'}:return {'instance_type':'t3.micro','root_gib':16,'data_gib':8}
    if code in {'T03','T04'}:return {'instance_type':'t3.micro','root_gib':16,'db_class':'db.t3.micro','db_gib':20,'min_instances':1,'max_instances':2 if code=='T04' else 1,'max_records':32,'max_record_bytes':256}
    if code=='T06':return {**S3_CONFIG,'cpu':256,'memory_mib':512,'tasks':1,'image':'operator-approved ECR digest'}
    if code=='T08':return {'instance_type':'t3.micro','root_gib':16,'nodes':2,'efs_encrypted':True,'max_records':32,'max_record_bytes':256}
    if code=='T09':return {'billing':'PAY_PER_REQUEST','max_records':32,'max_record_bytes':256,'lambda_memory_mib':128}
    if code=='T10':return {**S3_CONFIG,'base_rpu':8,'max_rpu':8,'daily_rpu_hours':8,'max_records':32,'max_record_bytes':256}
    raise ValueError('Unknown template')

def configuration_profiles(code):
    base=configuration(code)
    if code in {'T01','T05'}:
        extra={**base,'data_gib':16};label='Ổ dữ liệu 16 GiB';description='Máy t3.micro, root 16 GiB; chọn ổ dữ liệu 8 hoặc 16 GiB.'
    elif code in {'T02','T07'}:
        extra={**base,'max_files':64,'max_total_bytes':524288};label='Kho 64 file · tổng 512 KiB';description='Kho tự tăng theo dữ liệu; mỗi file tối đa 8 KiB. Chọn hạn mức 32 hoặc 64 file.'
    elif code in {'T03','T04'}:
        extra={**base,'db_gib':40};label='Cơ sở dữ liệu 40 GiB';description='Giữ loại máy và PostgreSQL hiện có; chọn dung lượng DB 20 hoặc 40 GiB.'
    elif code=='T06':
        extra={**base,'cpu':512,'memory_mib':1024};label='Docker 0,5 vCPU · RAM 1 GiB';description='Chọn 0,25 vCPU/512 MiB hoặc 0,5 vCPU/1 GiB. Một tác vụ; image do quản trị duyệt.'
    elif code=='T08':
        extra={**base,'root_gib':32};label='Hai máy · root 32 GiB mỗi máy';description='Hai máy t3.micro dùng chung EFS; chọn root 16 hoặc 32 GiB mỗi máy. EFS tăng theo dữ liệu.'
    elif code=='T09':
        extra={**base,'lambda_memory_mib':256};label='API · bộ nhớ Lambda 256 MiB';description='Chọn bộ nhớ Lambda 128 hoặc 256 MiB; DynamoDB tính theo sử dụng, không cấp trước ổ đĩa.'
    else:return [{'id':'standard','label':'Cấu hình chuẩn','configuration':base,'description':'Cấu hình cũ giữ nguyên.'}]
    base_labels={'T01':'Ổ dữ liệu 8 GiB','T05':'Ổ dữ liệu 8 GiB','T02':'Kho 32 file · tổng 256 KiB','T07':'Kho 32 file · tổng 256 KiB',
        'T03':'Cơ sở dữ liệu 20 GiB','T04':'Cơ sở dữ liệu 20 GiB','T06':'Docker 0,25 vCPU · RAM 512 MiB','T08':'Hai máy · root 16 GiB mỗi máy','T09':'API · bộ nhớ Lambda 128 MiB'}
    profiles=[{'id':'standard','label':base_labels[code],'configuration':base,'description':description},
            {'id':'expanded','label':label,'configuration':extra,'description':description}]
    if code in {'T02','T07'}:
        profiles.append({'id':'files','label':'Files: 5 MiB each / 50 MiB total','description':'Direct S3 uploads; separately verified configuration. Existing profiles are unchanged.',
            'configuration':{'max_files':100,'max_file_bytes':5*1024*1024,'max_total_bytes':50*1024*1024,'max_writes':256}})
    return profiles

def resolve_configuration(code,value=None):
    if value is None or value=={}:return configuration(code)
    if not isinstance(value,dict):raise HubError('INVALID_CONFIGURATION','Cấu hình phải là một gói trong danh mục.')
    # JSON type comparison rejects booleans passed as integer sizes and partial/mixed presets.
    value={k:int(v) if isinstance(v,Decimal) and v==v.to_integral_value() else v for k,v in value.items()}
    encoded=json.dumps(value,sort_keys=True,separators=(',',':'))
    for profile in configuration_profiles(code):
        if encoded==json.dumps(profile['configuration'],sort_keys=True,separators=(',',':')):
            return profile['configuration'].copy()
    raise HubError('INVALID_CONFIGURATION','Chọn đúng cấu hình được công bố; không nhận thông số, image hoặc quyền tùy ý.')

def configuration_key(code,value):
    return hashlib.sha256(json.dumps({'template_id':code,'configuration':resolve_configuration(code,value),'schema':1},sort_keys=True,separators=(',',':')).encode()).hexdigest()

def configuration_verified(code,value,verified,proofs=None):
    cfg=resolve_configuration(code,value)
    if code not in verified:return False
    if cfg==configuration(code):return True
    proof=(proofs or {}).get(configuration_key(code,cfg),{})
    return (isinstance(proof,dict) and proof.get('passed') is True
        and type(proof.get('provisioning_checks')) is int and proof['provisioning_checks']>=2
        and proof.get('backup_restore_verified') is True)

def environment_configuration(env):
    return resolve_configuration(env['template_id'],env.get('configuration'))

def catalog(verified=None,configuration_proofs=None):
    verified = set(verified if verified is not None else filter(None, os.getenv("VERIFIED_TEMPLATES", "").split(",")))
    return [{"template_id": code, "name": name, "purpose": purpose,"name_key":"template."+code+".name","purpose_key":"template."+code+".purpose", "services": services,
             "status": "AWS_VERIFIED" if code in verified and code in IMPLEMENTED else
                       "CODE_READY_UNVERIFIED" if code in IMPLEMENTED else "NOT_IMPLEMENTED",
             "create_enabled": code in verified and code in IMPLEMENTED,
             "configuration": configuration(code) if code in IMPLEMENTED else {},
             'configuration_options':[{**p,'create_enabled':configuration_verified(code,p['configuration'],verified,configuration_proofs),
                 'status':'AWS_VERIFIED' if configuration_verified(code,p['configuration'],verified,configuration_proofs) else 'CODE_READY_UNVERIFIED'} for p in configuration_profiles(code)],
             'backup_scope':SCOPES[code],'backup_scope_key':'scope.'+code,
             'operating_capabilities':{'modes':['AUTO_OFF','AUTO_RENEW'],'ending_policies':['PAUSE','BACKUP_RETIRE'] if code in {'T01','T05'} else ['BACKUP_RETIRE'],
                 'supports_pause':code in {'T01','T05'},'period_minutes_min':5,'period_minutes_max':480},
             "operations": ["create", "backup", "restore", "destroy", "audit"] if code in IMPLEMENTED else []}
            for code, name, purpose, services in NAMES if code in ACTIVE_TEMPLATES]
