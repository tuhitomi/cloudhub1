"""Owned file metadata and legacy inline writes; isolated direct uploads live in uploads.py."""
import base64
import hashlib
import re
from .catalog import S3_CONFIG, environment_configuration
from .errors import HubError

MIME_TYPES = {"text/html", "text/css", "text/plain", "application/javascript", "application/json",
              "image/png", "image/jpeg", "image/svg+xml", "image/webp", "application/pdf", "application/zip", "application/octet-stream", "text/csv"}

def error_code(exc):
    return getattr(exc, "response", {}).get("Error", {}).get("Code", "")

def validate_key(key):
    if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}", key) or any(
            part in {"", ".", "..", ".cloudhub"} for part in key.split("/")):
        raise HubError("INVALID_INPUT", "Tên file tối đa 128 ký tự; không dùng đường dẫn ngược hoặc .cloudhub.")
    return key

def validate_file(body):
    if not isinstance(body, dict) or set(body) != {"key", "content_base64", "content_type"}:
        raise HubError("INVALID_INPUT", "Cần key, content_base64 và content_type.")
    validate_key(body["key"])
    if body["content_type"] not in MIME_TYPES or not isinstance(body["content_base64"], str):
        raise HubError("INVALID_INPUT", "Định dạng file chưa được hỗ trợ.")
    try:
        data = base64.b64decode(body["content_base64"], validate=True)
    except (ValueError, TypeError):
        raise HubError("INVALID_INPUT", "Nội dung base64 không hợp lệ.")
    if len(data) > S3_CONFIG["max_file_bytes"]:
        raise HubError("FILE_QUOTA", "Mỗi file tối đa 8 KiB.", 413)
    return data

def bucket_name(env, settings):
    eid = env["environment_id"]
    if not re.fullmatch(r"env-[a-f0-9]{24}", eid):
        raise HubError("RESOURCE_SCOPE_MISMATCH", "ID môi trường không hợp lệ.", 409)
    return "cloudhub-" + settings["account_id"] + "-" + settings["region"] + "-" + eid[4:]

def assert_bucket(client, env, settings):
    name = bucket_name(env, settings)
    if env.get("bucket_name") and env["bucket_name"] != name:
        raise HubError("RESOURCE_SCOPE_MISMATCH", "Tên bucket không thuộc môi trường.", 409)
    try:
        tags = client.get_bucket_tagging(Bucket=name, ExpectedBucketOwner=settings["account_id"])["TagSet"]
    except Exception as exc:
        if error_code(exc) == "NoSuchBucket":
            return None
        raise
    tags = {t["Key"]: t["Value"] for t in tags}
    if tags.get("cloudhub:environment") != env["environment_id"] or tags.get("cloudhub:owner") != env["owner_id"] or tags.get("cloudhub:managed") != "true":
        raise HubError("RESOURCE_SCOPE_MISMATCH", "Bucket không có nhãn sở hữu phù hợp; giữ nguyên tài nguyên.", 409)
    return name

def objects(client, name, settings, limits=None, prefix=""):
    limits=limits or S3_CONFIG
    result = []
    for page in client.get_paginator("list_objects_v2").paginate(Bucket=name, **({"Prefix":prefix} if prefix else {}), ExpectedBucketOwner=settings["account_id"]):
        for item in page.get("Contents", []):
            logical=item["Key"][len(prefix):]
            if logical.startswith(".cloudhub/"):
                continue
            validate_key(logical)
            if item["Size"] > limits["max_file_bytes"]:
                raise HubError("FILE_QUOTA", "Nguồn có file vượt cấu hình; giữ dữ liệu để quản trị kiểm tra.", 409)
            result.append({"key": logical, "size": item["Size"]})
            if len(result) > limits["max_files"]:
                raise HubError("FILE_QUOTA", "Nguồn có quá nhiều file; giữ nguyên dữ liệu.", 409)
    if sum(r["size"] for r in result) > limits["max_total_bytes"]:
        raise HubError("FILE_QUOTA", "Tổng dữ liệu vượt hạn mức của cấu hình đã chọn.", 409)
    return sorted(result, key=lambda r: r["key"])

def read(client, bucket, key, account, version=None, limit=None, if_match=None):
    limit=limit or S3_CONFIG["max_file_bytes"]
    params = {"Bucket": bucket, "Key": key, "ExpectedBucketOwner": account}
    if version:
        params["VersionId"] = version
    if if_match:
        params["IfMatch"] = if_match
    response = client.get_object(**params)
    stream = response["Body"]
    try:
        content = stream.read(limit + 1)
    finally:
        stream.close()
    if len(content) > limit:
        raise HubError("FILE_QUOTA", "File exceeds its approved size limit.", 409)
    return content, response

class OwnedFiles:
    def __init__(self, service, settings, client=None):
        self.service, self.settings = service, settings
        self.root_settings=settings
        self.clients={}
        self.client=client or self.make_client(settings['region'])
        self.clients[settings['region']]=self.client

    def make_client(self,region):
        import boto3
        from botocore.config import Config
        return boto3.client('s3',region_name=region,config=Config(signature_version='s3v4',
            s3={'addressing_style':'virtual'},connect_timeout=1,read_timeout=2,retries={'total_max_attempts':1}))

    def prepare(self,env):
        from .regions import regional_settings
        self.settings=regional_settings(self.root_settings,{**env,'region':self.service.region_for(env)})
        region=self.settings['region']
        if region not in self.clients:self.clients[region]=self.make_client(region)
        self.client=self.clients[region]

    def list(self, owner, eid):
        env = self.service.owned("E", eid, owner)
        if env["template_id"] not in {'T02','T06','T07','T10'} or env["status"] != "READY" or (env.get("deadline") is not None and env["deadline"] <= self.service.clock()):
            raise HubError("INVALID_STATE", "Kho file chưa sẵn sàng hoặc phiên đã hết hạn.", 409)
        self.prepare(env)
        name = assert_bucket(self.client, env, self.settings)
        if not name:
            raise HubError("SOURCE_MISSING", "Không tìm thấy bucket nguồn.", 409)
        limits=environment_configuration(env)
        pending=None
        if str(env.get('lock','')).startswith('upload-'):
            row=self.service.owned('H',env['lock'],owner)
            if row.get('environment_id')!=eid:raise HubError('RESOURCE_SCOPE_MISMATCH','Pending upload does not belong to this environment.',409)
            pending={'upload_id':row['upload_id'],'status':row['status'],'expires_at':row['expires_at'],
                'complete_until':row['complete_until'],'key':row['file']['key'],'can_cancel':row['status']=='PENDING'}
        return {"items": objects(self.client, name, self.settings,limits,prefix=('.cloudhub/releases/'+env['draft_release_id']+'/') if env['template_id']=='T02' and env.get('draft_release_id') else env.get('active_release_prefix','')), "limits": {k:limits[k] for k in S3_CONFIG},
                'pending_upload':pending,
                'legacy_inline_max_file_bytes':S3_CONFIG['max_file_bytes'],
                'direct_upload_enabled':self.service.direct_upload_available(env) and env['template_id'] in {'T02','T07'} and (env['template_id']!='T02' or env.get('direct_upload_schema')==1), 'draft_release_id':env.get('draft_release_id'), 'active_release_id':env.get('active_release_id'), 'previous_release_id':env.get('previous_release_id'),
                'public_content_base':('/_cloudhub_site/'+env.get('active_release_id','initial')+'/') if env['template_id']=='T02' and env.get('direct_upload_schema')==1 and not env.get('draft_release_id') else None,
                'write_enabled':env['template_id']!='T02' or env.get('direct_upload_schema')!=1 or (self.service.direct_upload_available(env) and bool(env.get('draft_release_id'))),
                "writes_used": env.get("file_writes", 0)}

    def metadata(self,owner,eid,body):
        if set(body)!={'key'}:raise HubError('INVALID_INPUT','A file key is required.')
        key=validate_key(body['key']);env=self.service.owned('E',eid,owner)
        if env['status']!='READY' or env['template_id'] not in {'T02','T07'}:raise HubError('INVALID_STATE','File is not available.',409)
        self.prepare(env);bucket=assert_bucket(self.client,env,self.settings)
        prefix=('.cloudhub/releases/'+env['draft_release_id']+'/') if env['template_id']=='T02' and env.get('draft_release_id') else env.get('active_release_prefix','')
        item=self.client.head_object(Bucket=bucket,Key=prefix+key,ExpectedBucketOwner=self.settings['account_id'])
        return {'key':key,'version_id':item['VersionId'],'size':item['ContentLength']}

    def share(self,owner,eid,body):
        if set(body)!={'key'}:raise HubError('INVALID_INPUT','Cần tên file key.')
        key=validate_key(body['key']);env=self.service.owned('E',eid,owner)
        if env['template_id']!='T07' or env['status']!='READY' or env.get('lock') or (env.get('deadline') is not None and env['deadline']<=self.service.clock()):
            raise HubError('INVALID_STATE','Kho file chưa sẵn sàng hoặc đang xử lý.',409)
        self.prepare(env)
        bucket=assert_bucket(self.client,env,self.settings)
        if not bucket:raise HubError('SOURCE_MISSING','Không tìm thấy kho file.',409)
        metadata=self.client.head_object(Bucket=bucket,Key=key,ExpectedBucketOwner=self.settings['account_id'])
        seconds=min(900,int(float(env['deadline'])-float(self.service.clock())) if env.get('deadline') is not None else 900)
        if seconds<1:raise HubError('INVALID_STATE','Phiên đã hết hạn.',409)
        # Sign a fixed object version, so a later write cannot change shared content.
        params={'Bucket':bucket,'Key':key,
            'VersionId':metadata['VersionId'],'ResponseContentDisposition':'attachment'}
        url=self.client.generate_presigned_url('get_object',Params=params,ExpiresIn=seconds)
        return {'url':url,'expires_at':int(self.service.clock())+seconds,'key':key,
            'notice':'Ai có liên kết này có thể tải file cho tới thời hạn hoặc khi file bị thu hồi.'}

def sha(data):
    return hashlib.sha256(data).hexdigest()
