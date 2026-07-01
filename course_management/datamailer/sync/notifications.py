import logging
from typing import Any

import requests

from ..client import DatamailerConfig
from ..payloads.peer_review import (
    peer_review_assignment_notification_payload,
)
from ..payloads.project_outcomes import (
    project_passed_recipient_list_payload,
)
from ..payloads.registration_confirmations import (
    registration_confirmation_payload,
)
from ..payloads.scores import (
    homework_score_notification_payload,
    project_score_notification_payload,
)
from .recipient_list_send import (
    DatamailerNotificationErrorData,
    RecipientListSendSyncData,
    handle_recipient_list_notification_error,
    send_recipient_list_transactional_and_audit,
    sync_members_before_recipient_list_send_or_audit,
)
from .transactional import send_transactional_email

logger = logging.getLogger(__name__)


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
        return handle_recipient_list_notification_error(error_data)


def _send_homework_score_notification_if_ready(config, list_key, payload):
    sync_data = RecipientListSendSyncData(
        config=config,
        list_key=list_key,
        payload=payload,
        idempotency_key=f"{payload['idempotency_key']}:members",
        ordering_key=list_key,
        error="Datamailer metadata sync was not acknowledged",
    )
    if not sync_members_before_recipient_list_send_or_audit(sync_data):
        return None
    return send_recipient_list_transactional_and_audit(
        config, list_key, payload
    )


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
        return handle_recipient_list_notification_error(error_data)


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
    if not sync_members_before_recipient_list_send_or_audit(sync_data):
        return None
    if not _sync_project_passed_outcome_before_score_send(
        config, project, list_key, payload
    ):
        return None
    return send_recipient_list_transactional_and_audit(
        config, list_key, payload
    )


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
    return sync_members_before_recipient_list_send_or_audit(sync_data)


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
        return handle_recipient_list_notification_error(error_data)


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
    if not sync_members_before_recipient_list_send_or_audit(sync_data):
        return None
    return send_recipient_list_transactional_and_audit(
        config, list_key, payload
    )
