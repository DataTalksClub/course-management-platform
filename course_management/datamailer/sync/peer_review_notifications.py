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
