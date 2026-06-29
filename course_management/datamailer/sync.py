import logging
from dataclasses import dataclass
from typing import Any

import requests

from course_management.datamailer_outbox import (
    DatamailerOutboxEventData,
    enqueue_datamailer_outbox_event,
)
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


@dataclass(frozen=True)
class DatamailerNotificationErrorData:
    config: DatamailerConfig
    list_key: str
    payload: dict[str, Any]
    exc: requests.RequestException
    log_message: str
    object_id: int


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


@dataclass(frozen=True)
class ContactMembershipSyncData:
    config: DatamailerConfig
    contact_payload: dict[str, Any] | None
    list_payload: object
    label: str
    obj: object


@dataclass(frozen=True)
class RecipientListBulkUpsertData:
    config: DatamailerConfig
    list_key: str
    payload: dict[str, Any]
    idempotency_key: str
    ordering_key: str


@dataclass(frozen=True)
class RecipientListMembershipRemoveData:
    config: DatamailerConfig
    list_payloads: list
    label: str
    obj: object


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


def payload_with_configured_from_email(payload, config):
    if config.from_email and "from_email" not in payload:
        return payload | {"from_email": config.from_email}
    return payload


def handle_contact_sync_error(config, user):
    logger.exception(
        "Datamailer contact sync failed for user_id=%s",
        user.pk,
    )
    if config.strict:
        raise


def sync_contact(user, course=None) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    payload = contact_payload_for_user(user, course=course)
    if payload is None:
        return

    client = DatamailerClient(config)
    payload = payload_with_configured_from_email(payload, config)

    try:
        client.upsert_contact(payload)
    except requests.RequestException:
        handle_contact_sync_error(config, user)


def erase_contact_from_datamailer(
    user=None, *, user_id=None, email=None
) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    user_id, email = _contact_erase_target(
        user, user_id=user_id, email=email
    )
    if not email:
        return

    ordering_key = _contact_erase_ordering_key(user_id, email)
    _enqueue_contact_erase_event(
        config,
        user_id=user_id,
        email=email,
        ordering_key=ordering_key,
    )


def _contact_erase_target(user, *, user_id, email):
    user_id = _contact_erase_user_id(user, user_id)
    email = _contact_erase_email(user, email)
    return user_id, email


def _contact_erase_user_id(user, user_id):
    if user_id is None and user is not None:
        return user.pk
    return user_id


def _contact_erase_email(user, email):
    if email is None and user is not None:
        email = user.email
    return (email or "").strip().lower()


def _contact_erase_ordering_key(user_id, email):
    if user_id is not None:
        return f"user:{user_id}"
    return f"email:{email}"


def _enqueue_contact_erase_event(config, *, user_id, email, ordering_key):
    event_data = DatamailerOutboxEventData(
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
    enqueue_datamailer_outbox_event(event_data)


def _sync_contact_and_membership(data):
    """Upsert a contact and its recipient-list membership in one call.

    No-op if either payload is None.
    """
    if data.contact_payload is None or data.list_payload is None:
        return

    event_data = DatamailerOutboxEventData(
        event_type="recipient_list.member_upsert",
        idempotency_key=(
            "recipient-list.member-upsert:"
            f"{data.list_payload.list_key}:"
            f"{data.list_payload.source_object_key}:"
            f"{data.obj.pk}:{data.obj.__class__.__name__}"
        ),
        ordering_key=datamailer_ordering_key(data.obj),
        payload={
            "contact_payload": data.contact_payload,
            "list_key": data.list_payload.list_key,
            "source_object_key": data.list_payload.source_object_key,
            "member_payload": data.list_payload.payload,
            "label": data.label,
            "object_id": data.obj.pk,
        },
    )
    enqueue_datamailer_outbox_event(event_data)


def sync_registration_to_datamailer(registration) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    sync_data = ContactMembershipSyncData(
        config=config,
        contact_payload=registration_contact_payload(registration),
        list_payload=registration_recipient_list_payload(registration),
        label="registration",
        obj=registration,
    )
    _sync_contact_and_membership(sync_data)


def sync_enrollment_to_datamailer(enrollment) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    sync_data = ContactMembershipSyncData(
        config=config,
        contact_payload=contact_payload_for_user(
            enrollment.student, course=enrollment.course
        ),
        list_payload=enrollment_recipient_list_payload(enrollment),
        label="enrollment",
        obj=enrollment,
    )
    _sync_contact_and_membership(sync_data)


def sync_homework_submission_to_datamailer(submission) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    sync_data = ContactMembershipSyncData(
        config=config,
        contact_payload=contact_payload_for_user(
            submission.student, course=submission.homework.course
        ),
        list_payload=homework_submission_recipient_list_payload(submission),
        label="homework submission",
        obj=submission,
    )
    _sync_contact_and_membership(sync_data)


def sync_project_submission_to_datamailer(submission) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    sync_data = ContactMembershipSyncData(
        config=config,
        contact_payload=contact_payload_for_user(
            submission.student, course=submission.project.course
        ),
        list_payload=project_submission_recipient_list_payload(submission),
        label="project submission",
        obj=submission,
    )
    _sync_contact_and_membership(sync_data)


def sync_project_passed_outcome_to_datamailer(submission) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    outcome_payload = project_passed_recipient_list_member_payload(
        submission
    )
    if submission.passed:
        sync_data = ContactMembershipSyncData(
            config=config,
            contact_payload=contact_payload_for_user(
                submission.student, course=submission.project.course
            ),
            list_payload=outcome_payload,
            label="project passed outcome",
            obj=submission,
        )
        _sync_contact_and_membership(sync_data)
        return

    remove_data = RecipientListMembershipRemoveData(
        config=config,
        list_payloads=[outcome_payload],
        label="project passed outcome",
        obj=submission,
    )
    _remove_recipient_list_memberships(remove_data)


def enqueue_recipient_list_bulk_upsert(data):
    event_data = DatamailerOutboxEventData(
        event_type="recipient_list.members_bulk_upsert",
        idempotency_key=(
            "recipient-list.members-bulk-upsert:"
            f"{data.idempotency_key}"
        ),
        ordering_key=data.ordering_key,
        payload={
            "list_key": data.list_key,
            "member_sync_payload": recipient_list_member_sync_payload(
                data.config,
                data.payload,
            ),
        },
    )
    return enqueue_datamailer_outbox_event(event_data)


def bulk_upsert_recipient_list_members_before_send(data) -> bool:
    event = enqueue_recipient_list_bulk_upsert(data)
    return event.status == DatamailerOutboxStatus.ACKED


def _remove_recipient_list_memberships(data) -> None:
    for list_payload in data.list_payloads:
        if list_payload is None:
            continue
        event_data = DatamailerOutboxEventData(
            event_type="recipient_list.member_remove",
            idempotency_key=(
                "recipient-list.member-remove:"
                f"{list_payload.list_key}:"
                f"{list_payload.source_object_key}:"
                f"{data.obj.pk}:{data.obj.__class__.__name__}"
            ),
            ordering_key=datamailer_ordering_key(data.obj),
            payload={
                "list_key": list_payload.list_key,
                "source_object_key": list_payload.source_object_key,
                "member_payload": removed_recipient_list_member_payload(
                    list_payload.payload
                ),
                "label": data.label,
                "object_id": data.obj.pk,
            },
        )
        enqueue_datamailer_outbox_event(event_data)


def remove_registration_from_datamailer(registration) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    remove_data = RecipientListMembershipRemoveData(
        config=config,
        list_payloads=[registration_recipient_list_payload(registration)],
        label="registration",
        obj=registration,
    )
    _remove_recipient_list_memberships(remove_data)


def remove_enrollment_from_datamailer(enrollment) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    remove_data = RecipientListMembershipRemoveData(
        config=config,
        list_payloads=[
            enrollment_recipient_list_payload(enrollment),
            course_graduate_recipient_list_member_payload(enrollment),
        ],
        label="enrollment",
        obj=enrollment,
    )
    _remove_recipient_list_memberships(remove_data)


def remove_homework_submission_from_datamailer(submission) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    remove_data = RecipientListMembershipRemoveData(
        config=config,
        list_payloads=[homework_submission_recipient_list_payload(submission)],
        label="homework submission",
        obj=submission,
    )
    _remove_recipient_list_memberships(remove_data)


def remove_project_submission_from_datamailer(submission) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    list_payloads = [
        project_submission_recipient_list_payload(submission)
    ]
    if submission.passed:
        passed_payload = project_passed_recipient_list_member_payload(
            submission
        )
        list_payloads.append(passed_payload)
    remove_data = RecipientListMembershipRemoveData(
        config=config,
        list_payloads=list_payloads,
        label="project submission",
        obj=submission,
    )
    _remove_recipient_list_memberships(remove_data)


def datamailer_audit_status(error: str) -> str:
    if error:
        return DatamailerSendAuditStatus.FAILED
    return DatamailerSendAuditStatus.SUCCEEDED


def datamailer_audit_template_key(payload, response) -> str:
    return (
        response.get("template_key")
        or response.get("message", {}).get("template_key", "")
        or payload.get("template_key", "")
    )


def datamailer_audit_category_tag(payload, metadata) -> str:
    return payload.get("category_tag", "") or metadata.get("category_tag", "")


def datamailer_send_audit_defaults(data) -> dict[str, Any]:
    counts = datamailer_send_counts(
        data.send_type,
        data.payload,
        data.response,
    )
    return {
        "status": datamailer_audit_status(data.error),
        "template_key": datamailer_audit_template_key(
            data.payload,
            data.response,
        ),
        "category_tag": datamailer_audit_category_tag(
            data.payload,
            data.metadata,
        ),
        "list_key": datamailer_send_list_key(
            data.send_type,
            explicit_list_key=data.list_key,
            payload=data.payload,
            response=data.response,
        ),
        "source": data.metadata.get("source", ""),
        "event": data.metadata.get("event", ""),
        "intended_count": counts["intended_count"],
        "created_count": counts["created_count"],
        "enqueued_count": counts["enqueued_count"],
        "skipped_count": counts["skipped_count"],
        "idempotent_replay_count": counts["idempotent_replay_count"],
        "error": data.error,
        "response_payload": data.response,
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
    audit, _created = DatamailerSendAudit.objects.update_or_create(
        send_type=data.send_type,
        idempotency_key=idempotency_key,
        defaults=datamailer_send_audit_defaults(defaults_data),
    )
    return audit


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
    audit_data = DatamailerSendAuditData(
        send_type=DatamailerSendAuditType.RECIPIENT_LIST,
        payload=error_data.payload,
        list_key=error_data.list_key,
        error=str(error_data.exc),
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
    response = client.send_recipient_list_transactional(
        list_key, recipient_list_send_payload(payload)
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


def send_certificate_availability_notification(
    enrollment,
) -> dict[str, Any] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    notification_payloads = _certificate_availability_payloads(enrollment)
    if notification_payloads is None:
        return None

    graduate_list_payload, payload = notification_payloads
    try:
        return _send_certificate_availability_if_ready(
            config,
            enrollment,
            graduate_list_payload,
            payload,
        )
    except requests.RequestException as exc:
        return _handle_certificate_availability_send_error(
            config,
            enrollment,
            payload,
            exc,
        )


def _certificate_availability_payloads(enrollment):
    graduate_list_payload = course_graduate_recipient_list_payload(
        enrollment
    )
    payload = certificate_availability_notification_payload(enrollment)
    if graduate_list_payload is None and payload is None:
        return None
    return graduate_list_payload, payload


def _send_certificate_availability_if_ready(
    config,
    enrollment,
    graduate_list_payload,
    payload,
):
    if not _sync_graduate_outcome_before_certificate_send(
        config, enrollment, graduate_list_payload, payload
    ):
        return None
    if payload is None:
        return None
    return _send_transactional_and_audit(config, payload)


def _handle_certificate_availability_send_error(
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
        audit_data = DatamailerSendAuditData(
            send_type=DatamailerSendAuditType.TRANSACTIONAL,
            payload=payload,
            error=str(exc),
        )
        record_datamailer_send_audit(audit_data)
    if config.strict:
        raise
    return None


def _sync_graduate_outcome_before_certificate_send(
    config, enrollment, graduate_list_payload, payload
):
    if graduate_list_payload is None:
        return True

    list_key, list_payload = graduate_list_payload
    bulk_data = RecipientListBulkUpsertData(
        config=config,
        list_key=list_key,
        payload=list_payload,
        idempotency_key=_certificate_graduate_outcome_idempotency_key(
            payload, enrollment
        ),
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


def _certificate_graduate_outcome_idempotency_key(payload, enrollment):
    if payload is not None:
        return f"{payload['idempotency_key']}:graduate-outcome"
    return f"certificate-available:{enrollment.pk}:graduate-outcome"


def _send_transactional_and_audit(config, payload):
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

    payload = _transactional_payload_with_config_defaults(config, payload)
    try:
        return _send_transactional_and_audit(config, payload)
    except requests.RequestException as exc:
        return _handle_transactional_send_error(config, payload, exc)


def _transactional_payload_with_config_defaults(config, payload):
    if "audience" not in payload:
        payload = payload | {"audience": config.audience}
    if "client" not in payload:
        payload = payload | {"client": config.client}
    if config.from_email and "from_email" not in payload:
        payload = payload | {"from_email": config.from_email}
    return payload


def _handle_transactional_send_error(config, payload, exc):
    logger.exception("Datamailer transactional email failed")
    audit_data = DatamailerSendAuditData(
        send_type=DatamailerSendAuditType.TRANSACTIONAL,
        payload=payload,
        error=str(exc),
    )
    record_datamailer_send_audit(audit_data)
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
