import logging
from dataclasses import dataclass
from typing import Any

import requests

from data.models import DatamailerSendAuditType

from ..client import DatamailerClient, DatamailerConfig
from ..payloads.peer_review import (
    peer_review_assignment_notification_payload,
)
from ..payloads.project_outcomes import (
    project_passed_recipient_list_payload,
)
from ..payloads.registrations import (
    registration_confirmation_payload,
)
from ..payloads.scores import (
    homework_score_notification_payload,
    project_score_notification_payload,
)
from ..payloads.send import (
    recipient_list_send_payload,
)
from .audit import DatamailerSendAuditData, record_datamailer_send_audit
from .bulk import (
    RecipientListBulkUpsertData,
    bulk_upsert_recipient_list_members_before_send,
)
from .transactional import send_transactional_email

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


def send_registration_confirmation_email(
    registration,
) -> dict[str, Any] | None:
    payload = registration_confirmation_payload(registration)
    if payload is None:
        return None
    return send_transactional_email(payload)


def send_homework_score_notification(homework) -> dict[str, Any] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    list_payload = homework_score_notification_payload(homework)
    if list_payload is None:
        return None

    list_key, payload = list_payload
    try:
        return _send_homework_score_notification_if_ready(
            config, list_key, payload
        )
    except requests.RequestException as exc:
        error_data = DatamailerNotificationErrorData(
            config=config,
            list_key=list_key,
            payload=payload,
            exc=exc,
            log_message=(
                "Datamailer homework score notification failed "
                "for homework_id=%s"
            ),
            object_id=homework.pk,
        )
        return _handle_recipient_list_notification_error(error_data)


def _send_homework_score_notification_if_ready(config, list_key, payload):
    sync_data = RecipientListSendSyncData(
        config=config,
        list_key=list_key,
        payload=payload,
        idempotency_key=f"{payload['idempotency_key']}:members",
        ordering_key=list_key,
        error="Datamailer metadata sync was not acknowledged",
    )
    if not _sync_members_before_recipient_list_send_or_audit(sync_data):
        return None
    return _send_recipient_list_transactional_and_audit(
        config, list_key, payload
    )


def _handle_recipient_list_notification_error(error_data):
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


def send_project_score_notification(project) -> dict[str, Any] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    list_payload = project_score_notification_payload(project)
    if list_payload is None:
        return None

    list_key, payload = list_payload
    try:
        return _send_project_score_notification_if_ready(
            config, project, list_key, payload
        )
    except requests.RequestException as exc:
        error_data = DatamailerNotificationErrorData(
            config=config,
            list_key=list_key,
            payload=payload,
            exc=exc,
            log_message=(
                "Datamailer project score notification failed "
                "for project_id=%s"
            ),
            object_id=project.pk,
        )
        return _handle_recipient_list_notification_error(error_data)


def _send_project_score_notification_if_ready(
    config,
    project,
    list_key,
    payload,
):
    sync_data = RecipientListSendSyncData(
        config=config,
        list_key=list_key,
        payload=payload,
        idempotency_key=f"{payload['idempotency_key']}:members",
        ordering_key=list_key,
        error="Datamailer metadata sync was not acknowledged",
    )
    if not _sync_members_before_recipient_list_send_or_audit(sync_data):
        return None
    if not _sync_project_passed_outcome_before_score_send(
        config, project, list_key, payload
    ):
        return None
    return _send_recipient_list_transactional_and_audit(
        config, list_key, payload
    )


def _sync_members_before_recipient_list_send_or_audit(data):
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


def _sync_project_passed_outcome_before_score_send(
    config, project, list_key, payload
):
    passed_list_payload = project_passed_recipient_list_payload(project)
    if passed_list_payload is None:
        return True

    passed_list_key, passed_payload = passed_list_payload
    sync_data = RecipientListSendSyncData(
        config=config,
        list_key=passed_list_key,
        payload=passed_payload,
        idempotency_key=f"{payload['idempotency_key']}:passed-outcome",
        ordering_key=passed_list_key,
        error="Datamailer passed-outcome sync was not acknowledged",
        audit_payload=payload,
        audit_list_key=list_key,
    )
    return _sync_members_before_recipient_list_send_or_audit(sync_data)


def _send_recipient_list_transactional_and_audit(
    config, list_key, payload
):
    client = DatamailerClient(config)
    send_payload = recipient_list_send_payload(payload)
    response = client.send_recipient_list_transactional(
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


def send_peer_review_assignment_notification(
    project,
) -> dict[str, Any] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    list_payload = peer_review_assignment_notification_payload(project)
    if list_payload is None:
        return None

    list_key, payload = list_payload
    try:
        return _send_peer_review_assignment_notification_if_ready(
            config, list_key, payload
        )
    except requests.RequestException as exc:
        error_data = DatamailerNotificationErrorData(
            config=config,
            list_key=list_key,
            payload=payload,
            exc=exc,
            log_message=(
                "Datamailer peer review assignment notification failed "
                "for project_id=%s"
            ),
            object_id=project.pk,
        )
        return _handle_recipient_list_notification_error(error_data)


def _send_peer_review_assignment_notification_if_ready(
    config, list_key, payload
):
    sync_data = RecipientListSendSyncData(
        config=config,
        list_key=list_key,
        payload=payload,
        idempotency_key=f"{payload['idempotency_key']}:members",
        ordering_key=list_key,
        error="Datamailer metadata sync was not acknowledged",
    )
    if not _sync_members_before_recipient_list_send_or_audit(sync_data):
        return None
    return _send_recipient_list_transactional_and_audit(
        config, list_key, payload
    )
