import logging
from dataclasses import dataclass
from typing import Any

import requests

from data.models import DatamailerSendAuditType

from ..client import DatamailerClient, DatamailerConfig
from ..payloads.send import recipient_list_send_payload
from .audit import DatamailerSendAuditData, record_datamailer_send_audit
from .bulk import (
    RecipientListBulkUpsertData,
    bulk_upsert_recipient_list_members_before_send,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DatamailerNotificationErrorData:
    config: DatamailerConfig
    list_key: str
    payload: dict[str, Any]
    exc: requests.RequestException
    log_message: str
    object_id: int


@dataclass(frozen=True)
class RecipientListSendSyncData:
    config: DatamailerConfig
    list_key: str
    payload: dict[str, Any]
    idempotency_key: str
    ordering_key: str
    error: str
    audit_payload: dict[str, Any] | None = None
    audit_list_key: str | None = None


def handle_recipient_list_notification_error(error_data):
    logger.exception(error_data.log_message, error_data.object_id)
    error = str(error_data.exc)
    audit_data = DatamailerSendAuditData(
        send_type=DatamailerSendAuditType.RECIPIENT_LIST,
        payload=error_data.payload,
        list_key=error_data.list_key,
        error=error,
    )
    record_datamailer_send_audit(audit_data)
    if error_data.config.strict:
        raise
    return None


def sync_members_before_recipient_list_send_or_audit(data):
    bulk_data = RecipientListBulkUpsertData(
        config=data.config,
        list_key=data.list_key,
        payload=data.payload,
        idempotency_key=data.idempotency_key,
        ordering_key=data.ordering_key,
    )
    synced = bulk_upsert_recipient_list_members_before_send(bulk_data)
    if synced:
        return True

    audit_data = DatamailerSendAuditData(
        send_type=DatamailerSendAuditType.RECIPIENT_LIST,
        payload=data.audit_payload or data.payload,
        list_key=data.audit_list_key or data.list_key,
        error=data.error,
    )
    record_datamailer_send_audit(audit_data)
    return False


def send_recipient_list_transactional_and_audit(
    config, list_key, payload
):
    client = DatamailerClient(config)
    send_payload = recipient_list_send_payload(payload)
    response = client.recipient_lists.sends.send_to_list(
        list_key, send_payload
    )
    audit_data = DatamailerSendAuditData(
        send_type=DatamailerSendAuditType.RECIPIENT_LIST,
        payload=payload,
        list_key=list_key,
        response=response,
    )
    record_datamailer_send_audit(audit_data)
    return response
