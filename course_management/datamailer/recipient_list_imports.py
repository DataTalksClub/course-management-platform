from dataclasses import dataclass
import hashlib
import json
import re

import boto3
from django.conf import settings
from django.core.management.base import CommandError


@dataclass(frozen=True)
class ImportUploadBody:
    s3: object
    bucket: str
    key: str
    body: bytes
    metadata: dict


def import_member_jsonl(members):
    lines = []
    for member in members:
        line = json.dumps(member, sort_keys=True, separators=(",", ":"))
        lines.append(line)
    content = "\n".join(lines)
    content_with_trailing_newline = f"{content}\n"
    body = content_with_trailing_newline.encode("utf-8")
    return body


def safe_s3_key_part(value):
    stripped_value = value.strip()
    safe = re.sub(r"[^A-Za-z0-9._:@=-]+", "_", stripped_value)
    stripped_safe = safe.strip("._")
    if stripped_safe:
        return stripped_safe
    return "recipient-list"


def import_object_key(kind, config, list_key, content_sha256):
    import_prefix = getattr(settings, "DATAMAILER_IMPORT_S3_PREFIX", "")
    safe_list_key = safe_s3_key_part(list_key)
    parts = [
        import_prefix,
        config.client,
        config.audience,
        kind,
        safe_list_key,
        f"{content_sha256}.jsonl",
    ]
    key_parts = []
    for part in parts:
        if not part:
            continue
        key_part = part.strip("/")
        key_parts.append(key_part)
    return "/".join(key_parts)


def import_s3_bucket():
    bucket = getattr(settings, "DATAMAILER_IMPORT_S3_BUCKET", "")
    if not bucket:
        raise CommandError(
            "DATAMAILER_IMPORT_S3_BUCKET must be set when using "
            "--import-by-reference."
        )
    return bucket


def import_s3_client():
    region = getattr(settings, "DATAMAILER_IMPORT_S3_REGION", "")
    s3_kwargs = {}
    if region:
        s3_kwargs["region_name"] = region
    return boto3.client("s3", **s3_kwargs)


def import_file_metadata(config, list_key, content_sha256):
    encoded_list_key = list_key.encode("utf-8")
    list_key_sha256 = hashlib.sha256(encoded_list_key).hexdigest()
    return {
        "client": config.client,
        "audience": config.audience,
        "list-key-sha256": list_key_sha256,
        "content-sha256": content_sha256,
    }


def upload_import_body(upload_body):
    upload_body.s3.put_object(
        Bucket=upload_body.bucket,
        Key=upload_body.key,
        Body=upload_body.body,
        ContentType="application/x-ndjson",
        Metadata=upload_body.metadata,
    )


def presigned_import_url(s3, bucket, key):
    params = {"Bucket": bucket, "Key": key}
    expires_in = getattr(
        settings, "DATAMAILER_IMPORT_URL_EXPIRES_SECONDS", 3600
    )
    return s3.generate_presigned_url(
        "get_object",
        Params=params,
        ExpiresIn=expires_in,
        HttpMethod="GET",
    )


def upload_import_file(kind, config, list_key, payload):
    bucket = import_s3_bucket()
    body = import_member_jsonl(payload["members"])
    content_sha256 = hashlib.sha256(body).hexdigest()
    key = import_object_key(kind, config, list_key, content_sha256)
    s3 = import_s3_client()
    metadata = import_file_metadata(config, list_key, content_sha256)
    upload_body = ImportUploadBody(
        s3=s3,
        bucket=bucket,
        key=key,
        body=body,
        metadata=metadata,
    )
    upload_import_body(upload_body)
    source_url = presigned_import_url(s3, bucket, key)
    row_count = len(payload["members"])
    return {
        "source_url": source_url,
        "s3_bucket": bucket,
        "s3_key": key,
        "content_sha256": content_sha256,
        "row_count": row_count,
    }


def import_idempotency_key(
    kind, list_key, content_sha256, *, remove_absent
):
    if remove_absent:
        remove_absent_value = "true"
    else:
        remove_absent_value = "false"
    encoded_list_key = list_key.encode("utf-8")
    list_key_sha256 = hashlib.sha256(encoded_list_key).hexdigest()
    return (
        "cmp-recipient-list-import:"
        f"{kind}:{list_key_sha256}:{content_sha256}:"
        f"remove-absent-{remove_absent_value}"
    )
