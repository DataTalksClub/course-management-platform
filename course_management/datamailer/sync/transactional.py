import logging
from typing import Any

import requests

from data.models import DatamailerSendAuditType

from ..client import DatamailerClient, DatamailerConfig
from .audit import DatamailerSendAuditData, record_datamailer_send_audit


logger = logging.getLogger(__name__)


def send_transactional_and_audit(config, payload):
    client = DatamailerClient(config)
    response = client.send_transactional(payload)
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
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    payload = transactional_payload_with_config_defaults(config, payload)
    try:
        return send_transactional_and_audit(config, payload)
    except requests.RequestException as exc:
        return handle_transactional_send_error(config, payload, exc)


def transactional_payload_with_config_defaults(config, payload):
    if "audience" not in payload:
        payload = payload | {"audience": config.audience}
    if "client" not in payload:
        payload = payload | {"client": config.client}
    if config.from_email and "from_email" not in payload:
        payload = payload | {"from_email": config.from_email}
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
