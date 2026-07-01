from dataclasses import dataclass
from typing import Any

from course_management.datamailer_outbox import (
    DatamailerOutboxEventData,
    enqueue_datamailer_outbox_event,
)
from data.models import DatamailerOutboxStatus

from ..client import DatamailerConfig
from ..keys import datamailer_ordering_key
from ..payloads import (
    contact_payload_for_user,
    course_graduate_recipient_list_member_payload,
    enrollment_recipient_list_payload,
    homework_submission_recipient_list_payload,
    project_passed_recipient_list_member_payload,
    project_submission_recipient_list_payload,
    recipient_list_member_sync_payload,
    registration_contact_payload,
    registration_recipient_list_payload,
    removed_recipient_list_member_payload,
)

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

    list_payload = homework_submission_recipient_list_payload(submission)
    list_payloads = [list_payload]
    remove_data = RecipientListMembershipRemoveData(
        config=config,
        list_payloads=list_payloads,
        label="homework submission",
        obj=submission,
    )
    _remove_recipient_list_memberships(remove_data)


def remove_project_submission_from_datamailer(submission) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    list_payload = project_submission_recipient_list_payload(submission)
    list_payloads = [list_payload]
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
