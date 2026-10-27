"""Build the existing project score membership events without per-row SQL."""

from course_management.datamailer.client import DatamailerConfig
from course_management.datamailer.payloads.base import contact_payload_for_user
from course_management.datamailer.payloads.submissions import (
    project_submission_recipient_list_payload,
)
from course_management.datamailer.payloads.project_outcomes import (
    project_passed_recipient_list_member_payload,
)
from course_management.datamailer.sync.membership_events import (
    ContactMembershipSyncData,
    RecipientListMembershipRemoveData,
    contact_membership_event,
    removed_membership_events,
)
from course_management.datamailer_outbox import enqueue_datamailer_outbox_events


def sync_scored_project_submissions(submissions):
    if DatamailerConfig.from_settings() is None:
        return
    events = []
    for submission in submissions:
        contact = contact_payload_for_user(
            submission.student, course=submission.project.course,
        )
        submitter = project_submission_recipient_list_payload(submission)
        outcome = project_passed_recipient_list_member_payload(submission)
        for member, label, remove in (
            (submitter, "project submission", False),
            (outcome, "project passed outcome", not submission.passed),
        ):
            if remove:
                events.extend(removed_membership_events(
                    RecipientListMembershipRemoveData(
                        list_payloads=[member], label=label, obj=submission,
                    )
                ))
                continue
            event = contact_membership_event(ContactMembershipSyncData(
                contact_payload=contact, list_payload=member,
                label=label, obj=submission,
            ))
            if event is not None:
                events.append(event)
    enqueue_datamailer_outbox_events(events)
