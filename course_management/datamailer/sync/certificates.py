import logging
from typing import Any

import requests

from data.models import DatamailerSendAuditType

from ..client import DatamailerConfig
from ..payloads.certificate_availability import (
    certificate_availability_notification_payload,
)
from ..payloads.course_graduates import (
    course_graduate_recipient_list_payload,
)
from .audit import DatamailerSendAuditData, record_datamailer_send_audit
from .bulk import (
    RecipientListBulkUpsertData,
    bulk_upsert_recipient_list_members_before_send,
)
from .transactional import send_transactional_and_audit


logger = logging.getLogger(__name__)


def send_certificate_availability_notification(
    enrollment,
) -> dict[str, Any] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    notification_payloads = certificate_availability_payloads(enrollment)
    if notification_payloads is None:
        return None

    graduate_list_payload, payload = notification_payloads
    try:
        return send_certificate_availability_if_ready(
            config,
            enrollment,
            graduate_list_payload,
            payload,
        )
    except requests.RequestException as exc:
        return handle_certificate_availability_send_error(
            config,
            enrollment,
            payload,
            exc,
        )


def certificate_availability_payloads(enrollment):
    graduate_list_payload = course_graduate_recipient_list_payload(
        enrollment
    )
    payload = certificate_availability_notification_payload(enrollment)
    if graduate_list_payload is None and payload is None:
        return None
    return graduate_list_payload, payload


def send_certificate_availability_if_ready(
    config,
    enrollment,
    graduate_list_payload,
    payload,
):
    if not sync_graduate_outcome_before_certificate_send(
        config, enrollment, graduate_list_payload, payload
    ):
        return None
    if payload is None:
        return None
    return send_transactional_and_audit(config, payload)


def handle_certificate_availability_send_error(
    config,
    enrollment,
    payload,
    exc,
):
    logger.exception(
        "Datamailer certificate availability notification failed "
        "for enrollment_id=%s",
        enrollment.pk,
    )
    if payload is not None:
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


def sync_graduate_outcome_before_certificate_send(
    config, enrollment, graduate_list_payload, payload
):
    if graduate_list_payload is None:
        return True

    list_key, list_payload = graduate_list_payload
    idempotency_key = certificate_graduate_outcome_idempotency_key(
        payload, enrollment
    )
    bulk_data = RecipientListBulkUpsertData(
        config=config,
        list_key=list_key,
        payload=list_payload,
        idempotency_key=idempotency_key,
        ordering_key=list_key,
    )
    synced = bulk_upsert_recipient_list_members_before_send(bulk_data)
    if synced:
        return True

    if payload is not None:
        audit_data = DatamailerSendAuditData(
            send_type=DatamailerSendAuditType.TRANSACTIONAL,
            payload=payload,
            error="Datamailer graduate-outcome sync was not acknowledged",
        )
        record_datamailer_send_audit(audit_data)
    return False


def certificate_graduate_outcome_idempotency_key(payload, enrollment):
    if payload is not None:
        return f"{payload['idempotency_key']}:graduate-outcome"
    return f"certificate-available:{enrollment.pk}:graduate-outcome"
