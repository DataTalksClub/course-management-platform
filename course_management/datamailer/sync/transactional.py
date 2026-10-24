import logging
import uuid
from typing import Any

import requests
from django.conf import settings

from course_management.observability import record_event
from data.models import DatamailerSendAuditType

from ..client import (
    RELAY_CONFIG_MISSING,
    DatamailerClient,
    validate_relay_config,
)
from .audit import DatamailerSendAuditData, record_datamailer_send_audit


logger = logging.getLogger(__name__)


def send_transactional_and_audit(config, payload):
    client = DatamailerClient(config)
    response = client.transactional.send_transactional(payload)
    audit_data = DatamailerSendAuditData(
        send_type=DatamailerSendAuditType.TRANSACTIONAL,
        payload=payload,
        response=response,
    )
    record_datamailer_send_audit(audit_data)
    return response


def send_transactional_email(
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    is_valid, reason, config = validate_relay_config()
    if not is_valid or config is None:
        return handle_transactional_config_error(
            payload, reason or RELAY_CONFIG_MISSING
        )

    payload = transactional_payload_with_config_defaults(config, payload)
    try:
        return send_transactional_and_audit(config, payload)
    except requests.RequestException as exc:
        return handle_transactional_send_error(config, payload, exc)


def handle_transactional_config_error(
    payload: dict[str, Any],
    reason: str,
    send_type: str = DatamailerSendAuditType.TRANSACTIONAL,
) -> None:
    logger.error("Datamailer transactional email failed: %s", reason)
    payload_copy = dict(payload)
    if "client" not in payload_copy:
        client = getattr(settings, "RELAY_CLIENT", "")
        if client:
            payload_copy["client"] = client
    if "audience" not in payload_copy:
        audience = getattr(settings, "RELAY_AUDIENCE", "")
        if audience:
            payload_copy["audience"] = audience
    if not payload_copy.get("idempotency_key"):
        payload_copy["idempotency_key"] = f"transactional:relay-fail:{uuid.uuid4().hex}"

    audit_data = DatamailerSendAuditData(
        send_type=send_type,
        payload=payload_copy,
        error=reason,
    )
    record_datamailer_send_audit(audit_data)

    record_event(
        "datamailer.health_warning",
        properties={
            "error": reason,
            "send_type": send_type,
            "template_key": payload_copy.get("template_key", ""),
            "idempotency_key": payload_copy.get("idempotency_key", ""),
        },
    )
    record_event(
        "datamailer.transactional_send_failed",
        properties={
            "error": reason,
            "template_key": payload_copy.get("template_key", ""),
            "idempotency_key": payload_copy.get("idempotency_key", ""),
        },
    )

    if getattr(settings, "RELAY_STRICT", False):
        raise RuntimeError(f"Datamailer transactional email failed: {reason}")
    return None


def transactional_payload_with_config_defaults(config, payload):
    if "audience" not in payload:
        payload = payload | {"audience": config.audience}
    if "client" not in payload:
        payload = payload | {"client": config.client}
    if config.from_email and "from_email" not in payload:
        payload = payload | {"from_email": config.from_email}
    if config.transactional_dry_run and "dry_run" not in payload:
        payload = payload | {"dry_run": True}
    return payload


def handle_transactional_send_error(config, payload, exc):
    logger.exception("Datamailer transactional email failed")
    error = str(exc)
    audit_data = DatamailerSendAuditData(
        send_type=DatamailerSendAuditType.TRANSACTIONAL,
        payload=payload,
        error=error,
    )
    record_datamailer_send_audit(audit_data)
    if config.strict:
        raise
    return None


def notification_config_or_audit(template_key, object_id, *, recipient_list=False):
    """Validate before payload builders can silently return for missing config.

    Record the attempted notification's identity even when configuration is
    insufficient to construct its recipient payload.
    """
    valid, reason, config = validate_relay_config()
    if valid and config is not None:
        return config
    send_type = (
        DatamailerSendAuditType.RECIPIENT_LIST
        if recipient_list else DatamailerSendAuditType.TRANSACTIONAL
    )
    handle_transactional_config_error(
        {
            "template_key": template_key,
            "idempotency_key": f"relay-config:{template_key}:{object_id}",
            "metadata": {"source": "course-management-platform"},
        },
        reason or RELAY_CONFIG_MISSING,
        send_type=send_type,
    )
    return None
