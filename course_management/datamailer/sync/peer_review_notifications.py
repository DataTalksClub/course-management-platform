from dataclasses import dataclass
from typing import Any

import requests

from ..client import DatamailerConfig
from ..payloads.peer_review import (
    peer_review_assignment_notification_payload,
)
from .recipient_list_send import (
    DatamailerNotificationErrorData,
    RecipientListSendSyncData,
    handle_recipient_list_notification_error,
    send_recipient_list_transactional_and_audit,
    sync_members_before_recipient_list_send_or_audit,
)


@dataclass(frozen=True)
class PeerReviewAssignmentSendData:
    config: DatamailerConfig
    project: Any
    list_key: str
    payload: dict[str, Any]


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
    send_data = PeerReviewAssignmentSendData(
        config=config,
        project=project,
        list_key=list_key,
        payload=payload,
    )
    try:
        return _send_peer_review_assignment_notification_if_ready(send_data)
    except requests.RequestException as exc:
        return _handle_peer_review_assignment_notification_error(
            send_data,
            exc,
        )


def _send_peer_review_assignment_notification_if_ready(data):
    sync_data = RecipientListSendSyncData(
        config=data.config,
        list_key=data.list_key,
        payload=data.payload,
        idempotency_key=f"{data.payload['idempotency_key']}:members",
        ordering_key=data.list_key,
        error="Datamailer metadata sync was not acknowledged",
    )
    if not sync_members_before_recipient_list_send_or_audit(sync_data):
        return None
    return send_recipient_list_transactional_and_audit(
        data.config,
        data.list_key,
        data.payload,
    )


def _handle_peer_review_assignment_notification_error(data, exc):
    error_data = DatamailerNotificationErrorData(
        config=data.config,
        list_key=data.list_key,
        payload=data.payload,
        exc=exc,
        log_message=(
            "Datamailer peer review assignment notification failed "
            "for project_id=%s"
        ),
        object_id=data.project.pk,
    )
    return handle_recipient_list_notification_error(error_data)
