from ..client import DatamailerConfig
from ..payloads.base import enrollment_recipient_list_payload
from ..payloads.course_graduates import (
    course_graduate_recipient_list_member_payload,
)
from ..payloads.project_outcomes import (
    project_passed_recipient_list_member_payload,
)
from ..payloads.registration_members import (
    registration_recipient_list_payload,
)
from ..payloads.submissions import (
    homework_submission_recipient_list_payload,
    project_submission_recipient_list_payload,
)
from .membership_events import (
    RecipientListMembershipRemoveData,
    remove_recipient_list_memberships,
)


def remove_registration_from_datamailer(registration) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    list_payload = registration_recipient_list_payload(registration)
    list_payloads = [list_payload]
    remove_data = RecipientListMembershipRemoveData(
        list_payloads=list_payloads,
        label="registration",
        obj=registration,
    )
    remove_recipient_list_memberships(remove_data)


def remove_enrollment_from_datamailer(enrollment) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    enrollment_payload = enrollment_recipient_list_payload(enrollment)
    graduate_payload = course_graduate_recipient_list_member_payload(
        enrollment
    )
    list_payloads = [
        enrollment_payload,
        graduate_payload,
    ]
    remove_data = RecipientListMembershipRemoveData(
        list_payloads=list_payloads,
        label="enrollment",
        obj=enrollment,
    )
    remove_recipient_list_memberships(remove_data)


def remove_homework_submission_from_datamailer(submission) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    list_payload = homework_submission_recipient_list_payload(submission)
    list_payloads = [list_payload]
    remove_data = RecipientListMembershipRemoveData(
        list_payloads=list_payloads,
        label="homework submission",
        obj=submission,
    )
    remove_recipient_list_memberships(remove_data)


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
        list_payloads=list_payloads,
        label="project submission",
        obj=submission,
    )
    remove_recipient_list_memberships(remove_data)
