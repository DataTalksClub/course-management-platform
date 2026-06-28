import logging
from typing import Any

import requests

from course_management.datamailer_outbox import enqueue_datamailer_outbox_event
from data.models import (
    DatamailerOutboxStatus,
    DatamailerSendAudit,
    DatamailerSendAuditStatus,
    DatamailerSendAuditType,
)

from .client import DatamailerClient, DatamailerConfig
from .keys import datamailer_ordering_key
from .payloads import (
    certificate_availability_notification_payload,
    contact_payload_for_user,
    course_graduate_recipient_list_member_payload,
    course_graduate_recipient_list_payload,
    datamailer_send_counts,
    datamailer_send_list_key,
    enrollment_recipient_list_payload,
    homework_score_notification_payload,
    homework_submission_recipient_list_payload,
    project_passed_recipient_list_member_payload,
    project_passed_recipient_list_payload,
    project_score_notification_payload,
    project_submission_recipient_list_payload,
    peer_review_assignment_notification_payload,
    recipient_list_member_sync_payload,
    recipient_list_send_payload,
    registration_confirmation_payload,
    registration_contact_payload,
    registration_recipient_list_payload,
    removed_recipient_list_member_payload,
)

logger = logging.getLogger(__name__)


def send_registration_confirmation_email(
    registration,
) -> dict[str, Any] | None:
    payload = registration_confirmation_payload(registration)
    if payload is None:
        return None
    return send_transactional_email(payload)

def sync_contact(user, course=None) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    payload = contact_payload_for_user(user, course=course)
    if payload is None:
        return

    client = DatamailerClient(config)
    if config.from_email and "from_email" not in payload:
        payload = payload | {"from_email": config.from_email}

    try:
        client.upsert_contact(payload)
    except requests.RequestException:
        logger.exception(
            "Datamailer contact sync failed for user_id=%s",
            user.pk,
        )
        if config.strict:
            raise

def erase_contact_from_datamailer(user=None, *, user_id=None, email=None) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    if email is None and user is not None:
        email = user.email
    if user_id is None and user is not None:
        user_id = user.pk

    email = (email or "").strip().lower()
    if not email:
        return

    ordering_key = f"user:{user_id}" if user_id is not None else f"email:{email}"
    enqueue_datamailer_outbox_event(
        event_type="contact.erase",
        idempotency_key=f"contact.erase:{ordering_key}:{email}",
        ordering_key=ordering_key,
        payload={
            "email": email,
            "audience": config.audience,
            "client": config.client,
            "user_id": user_id,
        },
    )

def _sync_contact_and_membership(
    config, contact_payload, list_payload, *, label, id_field, obj
):
    """Upsert a contact and its recipient-list membership in one call.

    No-op if either payload is None. On request failure, logs with the
    given ``label``/``id_field`` context and re-raises when config.strict.
    """
    if contact_payload is None or list_payload is None:
        return

    list_key, source_object_key, payload = list_payload
    enqueue_datamailer_outbox_event(
        event_type="recipient_list.member_upsert",
        idempotency_key=(
            f"recipient-list.member-upsert:{list_key}:{source_object_key}:"
            f"{obj.pk}:{obj.__class__.__name__}"
        ),
        ordering_key=datamailer_ordering_key(obj),
        payload={
            "contact_payload": contact_payload,
            "list_key": list_key,
            "source_object_key": source_object_key,
            "member_payload": payload,
            "label": label,
            "object_id": obj.pk,
        },
    )

def sync_registration_to_datamailer(registration) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    _sync_contact_and_membership(
        config,
        registration_contact_payload(registration),
        registration_recipient_list_payload(registration),
        label="registration",
        id_field="registration_id",
        obj=registration,
    )

def sync_enrollment_to_datamailer(enrollment) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    _sync_contact_and_membership(
        config,
        contact_payload_for_user(
            enrollment.student, course=enrollment.course
        ),
        enrollment_recipient_list_payload(enrollment),
        label="enrollment",
        id_field="enrollment_id",
        obj=enrollment,
    )

def sync_homework_submission_to_datamailer(submission) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    _sync_contact_and_membership(
        config,
        contact_payload_for_user(
            submission.student, course=submission.homework.course
        ),
        homework_submission_recipient_list_payload(submission),
        label="homework submission",
        id_field="submission_id",
        obj=submission,
    )

def sync_project_submission_to_datamailer(submission) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    _sync_contact_and_membership(
        config,
        contact_payload_for_user(
            submission.student, course=submission.project.course
        ),
        project_submission_recipient_list_payload(submission),
        label="project submission",
        id_field="submission_id",
        obj=submission,
    )

def sync_project_passed_outcome_to_datamailer(submission) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    outcome_payload = project_passed_recipient_list_member_payload(submission)
    if submission.passed:
        _sync_contact_and_membership(
            config,
            contact_payload_for_user(
                submission.student, course=submission.project.course
            ),
            outcome_payload,
            label="project passed outcome",
            id_field="submission_id",
            obj=submission,
        )
        return

    _remove_recipient_list_memberships(
        config,
        [outcome_payload],
        label="project passed outcome",
        id_field="submission_id",
        obj=submission,
    )

def enqueue_recipient_list_bulk_upsert(
    *,
    config: DatamailerConfig,
    list_key: str,
    payload: dict[str, Any],
    idempotency_key: str,
    ordering_key: str,
):
    return enqueue_datamailer_outbox_event(
        event_type="recipient_list.members_bulk_upsert",
        idempotency_key=f"recipient-list.members-bulk-upsert:{idempotency_key}",
        ordering_key=ordering_key,
        payload={
            "list_key": list_key,
            "member_sync_payload": recipient_list_member_sync_payload(
                config, payload
            ),
        },
    )

def bulk_upsert_recipient_list_members_before_send(
    *,
    config: DatamailerConfig,
    list_key: str,
    payload: dict[str, Any],
    idempotency_key: str,
    ordering_key: str,
) -> bool:
    event = enqueue_recipient_list_bulk_upsert(
        config=config,
        list_key=list_key,
        payload=payload,
        idempotency_key=idempotency_key,
        ordering_key=ordering_key,
    )
    return event.status == DatamailerOutboxStatus.ACKED

def _remove_recipient_list_memberships(
    config,
    list_payloads,
    *,
    label,
    id_field,
    obj,
) -> None:
    for list_payload in list_payloads:
        if list_payload is None:
            continue
        list_key, source_object_key, payload = list_payload
        enqueue_datamailer_outbox_event(
            event_type="recipient_list.member_remove",
            idempotency_key=(
                f"recipient-list.member-remove:{list_key}:{source_object_key}:"
                f"{obj.pk}:{obj.__class__.__name__}"
            ),
            ordering_key=datamailer_ordering_key(obj),
            payload={
                "list_key": list_key,
                "source_object_key": source_object_key,
                "member_payload": removed_recipient_list_member_payload(
                    payload
                ),
                "label": label,
                "object_id": obj.pk,
            },
        )

def remove_registration_from_datamailer(registration) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    _remove_recipient_list_memberships(
        config,
        [registration_recipient_list_payload(registration)],
        label="registration",
        id_field="registration_id",
        obj=registration,
    )

def remove_enrollment_from_datamailer(enrollment) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    _remove_recipient_list_memberships(
        config,
        [
            enrollment_recipient_list_payload(enrollment),
            course_graduate_recipient_list_member_payload(enrollment),
        ],
        label="enrollment",
        id_field="enrollment_id",
        obj=enrollment,
    )

def remove_homework_submission_from_datamailer(submission) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    _remove_recipient_list_memberships(
        config,
        [homework_submission_recipient_list_payload(submission)],
        label="homework submission",
        id_field="submission_id",
        obj=submission,
    )

def remove_project_submission_from_datamailer(submission) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    list_payloads = [project_submission_recipient_list_payload(submission)]
    if submission.passed:
        list_payloads.append(
            project_passed_recipient_list_member_payload(submission)
        )
    _remove_recipient_list_memberships(
        config,
        list_payloads,
        label="project submission",
        id_field="submission_id",
        obj=submission,
    )

def record_datamailer_send_audit(
    *,
    send_type: str,
    payload: dict[str, Any],
    list_key: str = "",
    response: dict[str, Any] | None = None,
    error: str = "",
) -> DatamailerSendAudit | None:
    idempotency_key = payload.get("idempotency_key", "")
    if not idempotency_key:
        return None

    response = response or {}
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}

    counts = datamailer_send_counts(send_type, payload, response)
    audit, _created = DatamailerSendAudit.objects.update_or_create(
        send_type=send_type,
        idempotency_key=idempotency_key,
        defaults={
            "status": (
                DatamailerSendAuditStatus.FAILED
                if error
                else DatamailerSendAuditStatus.SUCCEEDED
            ),
            "template_key": (
                response.get("template_key")
                or response.get("message", {}).get("template_key", "")
                or payload.get("template_key", "")
            ),
            "category_tag": payload.get("category_tag", "")
            or metadata.get("category_tag", ""),
            "list_key": datamailer_send_list_key(
                send_type,
                explicit_list_key=list_key,
                payload=payload,
                response=response,
            ),
            "source": metadata.get("source", ""),
            "event": metadata.get("event", ""),
            "intended_count": counts["intended_count"],
            "created_count": counts["created_count"],
            "enqueued_count": counts["enqueued_count"],
            "skipped_count": counts["skipped_count"],
            "idempotent_replay_count": counts["idempotent_replay_count"],
            "error": error,
            "response_payload": response,
        },
    )
    return audit

def send_homework_score_notification(homework) -> dict[str, Any] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    list_payload = homework_score_notification_payload(homework)
    if list_payload is None:
        return None

    try:
        list_key, payload = list_payload
        if not bulk_upsert_recipient_list_members_before_send(
            config=config,
            list_key=list_key,
            payload=payload,
            idempotency_key=f"{payload['idempotency_key']}:members",
            ordering_key=list_key,
        ):
            record_datamailer_send_audit(
                send_type=DatamailerSendAuditType.RECIPIENT_LIST,
                payload=payload,
                list_key=list_key,
                error="Datamailer metadata sync was not acknowledged",
            )
            return None
        client = DatamailerClient(config)
        response = client.send_recipient_list_transactional(
            list_key, recipient_list_send_payload(payload)
        )
        record_datamailer_send_audit(
            send_type=DatamailerSendAuditType.RECIPIENT_LIST,
            payload=payload,
            list_key=list_key,
            response=response,
        )
        return response
    except requests.RequestException as exc:
        logger.exception(
            "Datamailer homework score notification failed for homework_id=%s",
            homework.pk,
        )
        record_datamailer_send_audit(
            send_type=DatamailerSendAuditType.RECIPIENT_LIST,
            payload=payload,
            list_key=list_key if "list_key" in locals() else "",
            error=str(exc),
        )
        if config.strict:
            raise
        return None

def send_project_score_notification(project) -> dict[str, Any] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    list_payload = project_score_notification_payload(project)
    if list_payload is None:
        return None

    try:
        list_key, payload = list_payload
        passed_list_payload = project_passed_recipient_list_payload(project)
        if not bulk_upsert_recipient_list_members_before_send(
            config=config,
            list_key=list_key,
            payload=payload,
            idempotency_key=f"{payload['idempotency_key']}:members",
            ordering_key=list_key,
        ):
            record_datamailer_send_audit(
                send_type=DatamailerSendAuditType.RECIPIENT_LIST,
                payload=payload,
                list_key=list_key,
                error="Datamailer metadata sync was not acknowledged",
            )
            return None
        if passed_list_payload is not None:
            passed_list_key, passed_payload = passed_list_payload
            if not bulk_upsert_recipient_list_members_before_send(
                config=config,
                list_key=passed_list_key,
                payload=passed_payload,
                idempotency_key=(
                    f"{payload['idempotency_key']}:passed-outcome"
                ),
                ordering_key=passed_list_key,
            ):
                record_datamailer_send_audit(
                    send_type=DatamailerSendAuditType.RECIPIENT_LIST,
                    payload=payload,
                    list_key=list_key,
                    error="Datamailer passed-outcome sync was not acknowledged",
                )
                return None
        client = DatamailerClient(config)
        response = client.send_recipient_list_transactional(
            list_key, recipient_list_send_payload(payload)
        )
        record_datamailer_send_audit(
            send_type=DatamailerSendAuditType.RECIPIENT_LIST,
            payload=payload,
            list_key=list_key,
            response=response,
        )
        return response
    except requests.RequestException as exc:
        logger.exception(
            "Datamailer project score notification failed for project_id=%s",
            project.pk,
        )
        record_datamailer_send_audit(
            send_type=DatamailerSendAuditType.RECIPIENT_LIST,
            payload=payload,
            list_key=list_key if "list_key" in locals() else "",
            error=str(exc),
        )
        if config.strict:
            raise
        return None

def send_peer_review_assignment_notification(
    project,
) -> dict[str, Any] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    list_payload = peer_review_assignment_notification_payload(project)
    if list_payload is None:
        return None

    try:
        list_key, payload = list_payload
        if not bulk_upsert_recipient_list_members_before_send(
            config=config,
            list_key=list_key,
            payload=payload,
            idempotency_key=f"{payload['idempotency_key']}:members",
            ordering_key=list_key,
        ):
            record_datamailer_send_audit(
                send_type=DatamailerSendAuditType.RECIPIENT_LIST,
                payload=payload,
                list_key=list_key,
                error="Datamailer metadata sync was not acknowledged",
            )
            return None
        client = DatamailerClient(config)
        response = client.send_recipient_list_transactional(
            list_key,
            recipient_list_send_payload(payload),
        )
        record_datamailer_send_audit(
            send_type=DatamailerSendAuditType.RECIPIENT_LIST,
            payload=payload,
            list_key=list_key,
            response=response,
        )
        return response
    except requests.RequestException as exc:
        logger.exception(
            "Datamailer peer review assignment notification failed "
            "for project_id=%s",
            project.pk,
        )
        record_datamailer_send_audit(
            send_type=DatamailerSendAuditType.RECIPIENT_LIST,
            payload=payload,
            list_key=list_key if "list_key" in locals() else "",
            error=str(exc),
        )
        if config.strict:
            raise
        return None

def send_certificate_availability_notification(
    enrollment,
) -> dict[str, Any] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    graduate_list_payload = course_graduate_recipient_list_payload(enrollment)
    payload = certificate_availability_notification_payload(enrollment)
    if graduate_list_payload is None and payload is None:
        return None

    try:
        if graduate_list_payload is not None:
            list_key, list_payload = graduate_list_payload
            if not bulk_upsert_recipient_list_members_before_send(
                config=config,
                list_key=list_key,
                payload=list_payload,
                idempotency_key=(
                    f"{payload['idempotency_key']}:graduate-outcome"
                    if payload is not None
                    else f"certificate-available:{enrollment.pk}:graduate-outcome"
                ),
                ordering_key=list_key,
            ):
                if payload is not None:
                    record_datamailer_send_audit(
                        send_type=DatamailerSendAuditType.TRANSACTIONAL,
                        payload=payload,
                        error="Datamailer graduate-outcome sync was not acknowledged",
                    )
                return None
        if payload is None:
            return None
        client = DatamailerClient(config)
        response = client.send_transactional(payload)
        record_datamailer_send_audit(
            send_type=DatamailerSendAuditType.TRANSACTIONAL,
            payload=payload,
            response=response,
        )
        return response
    except requests.RequestException as exc:
        logger.exception(
            "Datamailer certificate availability notification failed "
            "for enrollment_id=%s",
            enrollment.pk,
        )
        if payload is not None:
            record_datamailer_send_audit(
                send_type=DatamailerSendAuditType.TRANSACTIONAL,
                payload=payload,
                error=str(exc),
            )
        if config.strict:
            raise
        return None

def send_transactional_email(
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    client = DatamailerClient(config)
    if "audience" not in payload:
        payload = payload | {"audience": config.audience}
    if "client" not in payload:
        payload = payload | {"client": config.client}
    if config.from_email and "from_email" not in payload:
        payload = payload | {"from_email": config.from_email}

    try:
        response = client.send_transactional(payload)
        record_datamailer_send_audit(
            send_type=DatamailerSendAuditType.TRANSACTIONAL,
            payload=payload,
            response=response,
        )
        return response
    except requests.RequestException as exc:
        logger.exception("Datamailer transactional email failed")
        record_datamailer_send_audit(
            send_type=DatamailerSendAuditType.TRANSACTIONAL,
            payload=payload,
            error=str(exc),
        )
        if config.strict:
            raise
        return None

def get_contact_status(email: str) -> dict[str, Any] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    client = DatamailerClient(config)

    try:
        return client.contact_status(email)
    except requests.RequestException:
        logger.exception("Datamailer contact status lookup failed")
        if config.strict:
            raise
        return None

def get_contact_history(
    contact_id: int,
    *,
    limit: int = 25,
) -> dict[str, Any] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    client = DatamailerClient(config)

    try:
        return client.contact_history(contact_id, limit=limit)
    except requests.RequestException:
        logger.exception("Datamailer contact history lookup failed")
        if config.strict:
            raise
        return None

def get_email_status(
    email: str, *, limit: int = 25
) -> dict[str, Any] | None:
    status = get_contact_status(email)
    if status is None:
        return None

    contact_id = status.get("contact_id")
    history = None
    if contact_id:
        history = get_contact_history(int(contact_id), limit=limit)

    return {
        "status": status,
        "history": history,
    }

def get_transactional_message_status(
    message_id: int,
) -> dict[str, Any] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    client = DatamailerClient(config)

    try:
        return client.transactional_message_status(message_id)
    except requests.RequestException:
        logger.exception(
            "Datamailer transactional message status lookup failed"
        )
        if config.strict:
            raise
        return None
