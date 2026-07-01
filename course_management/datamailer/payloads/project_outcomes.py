from typing import Any

from ..client import DatamailerConfig
from ..keys import project_passed_list_key
from .base import (
    RecipientListMemberPayload,
    recipient_list_send_member_payload,
)
from .bulk import bulk_recipient_list_payload
from .submissions import project_submission_recipient_list_payload


def project_passed_recipient_list_payload(
    project,
) -> tuple[str, dict[str, Any]] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    list_key = project_passed_list_key(project)
    payload = bulk_recipient_list_payload(
        config,
        project_passed_list_data(project),
        project_passed_members(project),
    )
    return list_key, payload


def project_passed_list_data(project) -> dict[str, Any]:
    course = project.course
    return {
        "type": "custom",
        "name": f"{course.title} {project.title} passed learners",
        "metadata": {
            "course_slug": course.slug,
            "project_slug": project.slug,
            "project_id": project.pk,
            "outcome": "project_passed",
        },
    }


def project_passed_members(project) -> list[dict[str, Any]]:
    members = []
    seen_students = set()
    candidate_submissions = project_passed_candidate_submissions(project)
    for submission in candidate_submissions:
        if submission.student_id in seen_students:
            continue
        seen_students.add(submission.student_id)
        member = project_passed_member(submission)
        if member is not None:
            members.append(member)
    return members


def project_passed_candidate_submissions(project):
    return project.projectsubmission_set.select_related(
        "student", "project__course"
    ).order_by("student_id", "-submitted_at", "-id")


def project_passed_member(submission) -> dict[str, Any] | None:
    if not submission.passed:
        return None

    item = project_submission_recipient_list_payload(submission)
    if item is None:
        return None

    member_payload = item.payload
    member = recipient_list_send_member_payload(
        item.source_object_key, member_payload
    )
    member["metadata"] = member["metadata"] | {
        "outcome": "project_passed",
    }
    return member


def project_passed_member_payload(project, payload) -> dict[str, Any]:
    return {
        **payload,
        "list": project_passed_list_data(project),
        "member": project_passed_member_payload_data(payload),
    }


def project_passed_member_payload_data(payload) -> dict[str, Any]:
    return {
        **payload["member"],
        "metadata": project_passed_member_metadata(payload),
    }


def project_passed_member_metadata(payload) -> dict[str, Any]:
    return payload["member"]["metadata"] | {
        "outcome": "project_passed",
    }


def project_passed_recipient_list_member_payload(
    submission,
) -> RecipientListMemberPayload | None:
    item = project_submission_recipient_list_payload(submission)
    if item is None:
        return None

    project = submission.project
    payload = item.payload
    member_payload = project_passed_member_payload(project, payload)
    return RecipientListMemberPayload(
        list_key=project_passed_list_key(project),
        source_object_key=item.source_object_key,
        payload=member_payload,
    )
