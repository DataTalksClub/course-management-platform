from ..client import DatamailerConfig
from ..payloads.base import (
    contact_payload_for_user,
    enrollment_recipient_list_payload,
)
from ..payloads.project_outcomes import (
    project_passed_recipient_list_member_payload,
)
from ..payloads.registration_contacts import (
    registration_contact_payload,
)
from ..payloads.registration_members import (
    registration_recipient_list_payload,
)
from ..payloads.submissions import (
    homework_submission_recipient_list_payload,
    project_submission_recipient_list_payload,
)
from .membership_events import (
    ContactMembershipSyncData,
    RecipientListMembershipRemoveData,
    remove_recipient_list_memberships,
    sync_contact_and_membership,
)


def sync_registration_to_datamailer(registration) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    contact_payload = registration_contact_payload(registration)
    list_payload = registration_recipient_list_payload(registration)
    sync_data = ContactMembershipSyncData(
        contact_payload=contact_payload,
        list_payload=list_payload,
        label="registration",
        obj=registration,
    )
    sync_contact_and_membership(sync_data)


def sync_enrollment_to_datamailer(enrollment) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    contact_payload = contact_payload_for_user(
        enrollment.student, course=enrollment.course
    )
    list_payload = enrollment_recipient_list_payload(enrollment)
    sync_data = ContactMembershipSyncData(
        contact_payload=contact_payload,
        list_payload=list_payload,
        label="enrollment",
        obj=enrollment,
    )
    sync_contact_and_membership(sync_data)


def sync_homework_submission_to_datamailer(submission) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    course = submission.homework.course
    contact_payload = contact_payload_for_user(
        submission.student,
        course=course,
    )
    list_payload = homework_submission_recipient_list_payload(submission)
    sync_data = ContactMembershipSyncData(
        contact_payload=contact_payload,
        list_payload=list_payload,
        label="homework submission",
        obj=submission,
    )
    sync_contact_and_membership(sync_data)


def sync_project_submission_to_datamailer(submission) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    course = submission.project.course
    contact_payload = contact_payload_for_user(
        submission.student,
        course=course,
    )
    list_payload = project_submission_recipient_list_payload(submission)
    sync_data = ContactMembershipSyncData(
        contact_payload=contact_payload,
        list_payload=list_payload,
        label="project submission",
        obj=submission,
    )
    sync_contact_and_membership(sync_data)


def _sync_project_passed_membership(submission, outcome_payload) -> None:
    course = submission.project.course
    contact_payload = contact_payload_for_user(
        submission.student,
        course=course,
    )
    sync_data = ContactMembershipSyncData(
        contact_payload=contact_payload,
        list_payload=outcome_payload,
        label="project passed outcome",
        obj=submission,
    )
    sync_contact_and_membership(sync_data)


def _remove_project_passed_membership(submission, outcome_payload) -> None:
    list_payloads = [outcome_payload]
    remove_data = RecipientListMembershipRemoveData(
        list_payloads=list_payloads,
        label="project passed outcome",
        obj=submission,
    )
    remove_recipient_list_memberships(remove_data)


def sync_project_passed_outcome_to_datamailer(submission) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    outcome_payload = project_passed_recipient_list_member_payload(
        submission
    )
    if submission.passed:
        _sync_project_passed_membership(submission, outcome_payload)
        return

    _remove_project_passed_membership(submission, outcome_payload)
