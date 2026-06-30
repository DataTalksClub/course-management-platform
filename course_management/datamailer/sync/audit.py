from dataclasses import dataclass
from typing import Any

from data.models import (
    DatamailerSendAudit,
    DatamailerSendAuditStatus,
)

from ..payloads import (
    datamailer_send_counts,
    datamailer_send_list_key,
)


@dataclass(frozen=True)
class DatamailerSendAuditData:
    send_type: str
    payload: dict[str, Any]
    list_key: str = ""
    response: dict[str, Any] | None = None
    error: str = ""


@dataclass(frozen=True)
class DatamailerSendAuditDefaultsData:
    send_type: str
    payload: dict[str, Any]
    list_key: str
    response: dict[str, Any]
    error: str
    metadata: dict[str, Any]


def datamailer_audit_status(error: str) -> str:
    if error:
        return DatamailerSendAuditStatus.FAILED
    return DatamailerSendAuditStatus.SUCCEEDED


def datamailer_audit_template_key(payload, response) -> str:
    response_template_key = response.get("template_key")
    message = response.get("message") or {}
    message_template_key = message.get("template_key", "")
    payload_template_key = payload.get("template_key", "")
    if response_template_key:
        return response_template_key
    if message_template_key:
        return message_template_key
    return payload_template_key


def datamailer_audit_category_tag(payload, metadata) -> str:
    payload_category_tag = payload.get("category_tag", "")
    metadata_category_tag = metadata.get("category_tag", "")
    if payload_category_tag:
        return payload_category_tag
    return metadata_category_tag


def datamailer_send_audit_defaults(data) -> dict[str, Any]:
    defaults = datamailer_send_audit_base_defaults(data)
    count_defaults = datamailer_send_audit_count_defaults(data)
    defaults.update(count_defaults)
    return defaults


def datamailer_send_audit_base_defaults(data) -> dict[str, Any]:
    list_key = datamailer_send_list_key(
        data.send_type,
        explicit_list_key=data.list_key,
        payload=data.payload,
        response=data.response,
    )
    template_key = datamailer_audit_template_key(
        data.payload,
        data.response,
    )
    category_tag = datamailer_audit_category_tag(
        data.payload,
        data.metadata,
    )
    status = datamailer_audit_status(data.error)
    source = data.metadata.get("source", "")
    event = data.metadata.get("event", "")
    return {
        "status": status,
        "template_key": template_key,
        "category_tag": category_tag,
        "list_key": list_key,
        "source": source,
        "event": event,
        "error": data.error,
        "response_payload": data.response,
    }


def datamailer_send_audit_count_defaults(data) -> dict[str, int]:
    counts = datamailer_send_counts(
        data.send_type,
        data.payload,
        data.response,
    )
    return {
        "intended_count": counts["intended_count"],
        "created_count": counts["created_count"],
        "enqueued_count": counts["enqueued_count"],
        "skipped_count": counts["skipped_count"],
        "idempotent_replay_count": counts["idempotent_replay_count"],
    }


def record_datamailer_send_audit(data) -> DatamailerSendAudit | None:
    idempotency_key = data.payload.get("idempotency_key", "")
    if not idempotency_key:
        return None

    response = data.response or {}
    metadata = data.payload.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    defaults_data = DatamailerSendAuditDefaultsData(
        send_type=data.send_type,
        payload=data.payload,
        list_key=data.list_key,
        response=response,
        error=data.error,
        metadata=metadata,
    )
    defaults = datamailer_send_audit_defaults(defaults_data)
    audit, _created = DatamailerSendAudit.objects.update_or_create(
        send_type=data.send_type,
        idempotency_key=idempotency_key,
        defaults=defaults,
    )
    return audit
