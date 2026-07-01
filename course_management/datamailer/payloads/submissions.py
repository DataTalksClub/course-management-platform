from typing import Any

from django.urls import reverse

from ..client import public_url
from ..keys import (
    homework_submitters_list_key,
    project_submitters_list_key,
)
from .base import (
    RecipientListMemberPayload,
    RecipientListMemberPayloadData,
    recipient_list_member_payload,
)


def homework_submission_recipient_list_payload(
    submission,
) -> RecipientListMemberPayload | None:
    email_value = submission.student.email or ""
    stripped_email = email_value.strip()
    email = stripped_email.lower()
    if not email:
        return None

    homework = submission.homework
    course = homework.course
    list_key = homework_submitters_list_key(homework)
    source_object_key = f"homework-submission:{submission.pk}"
    metadata = homework_submission_metadata(submission)
    payload_data = RecipientListMemberPayloadData(
        list_type="homework_submitters",
        list_name=f"{course.title} {homework.title} submitters",
        email=email,
        source_object_key=source_object_key,
        metadata=metadata,
    )
    payload = recipient_list_member_payload(payload_data)
    if payload is None:
        return None
    return RecipientListMemberPayload(
        list_key=list_key,
        source_object_key=source_object_key,
        payload=payload,
    )


def homework_submission_metadata(submission) -> dict[str, Any]:
    homework = submission.homework
    course = homework.course
    submitted_at = ""
    if submission.submitted_at:
        submitted_at = submission.submitted_at.isoformat()
    homework_url = homework_public_url(homework)
    return {
        "submission_id": submission.pk,
        "user_id": submission.student_id,
        "course_slug": course.slug,
        "homework_slug": homework.slug,
        "submitted_at": submitted_at,
        "questions_score": submission.questions_score,
        "learning_in_public_score": submission.learning_in_public_score,
        "faq_score": submission.faq_score,
        "total_score": submission.total_score,
        "homework_url": homework_url,
    }


def homework_public_url(homework):
    homework_path = reverse(
        "homework",
        kwargs={
            "course_slug": homework.course.slug,
            "homework_slug": homework.slug,
        },
    )
    homework_url = public_url(homework_path)
    return homework_url


def project_submission_metadata(submission) -> dict[str, Any]:
    return {
        **project_submission_identity_metadata(submission),
        **project_submission_score_metadata(submission),
        **project_submission_source_metadata(submission),
        **project_submission_status_metadata(submission),
    }


def project_submission_identity_metadata(submission) -> dict[str, Any]:
    project = submission.project
    course = project.course
    submitted_at = ""
    if submission.submitted_at:
        submitted_at = submission.submitted_at.isoformat()
    return {
        "submission_id": submission.pk,
        "user_id": submission.student_id,
        "course_slug": course.slug,
        "project_slug": project.slug,
        "submitted_at": submitted_at,
    }


def project_submission_score_metadata(submission) -> dict[str, Any]:
    return {
        "project_score": submission.project_score,
        "project_learning_in_public_score": (
            submission.project_learning_in_public_score
        ),
        "project_faq_score": submission.project_faq_score,
        "peer_review_score": submission.peer_review_score,
        "peer_review_learning_in_public_score": (
            submission.peer_review_learning_in_public_score
        ),
        "total_score": submission.total_score,
    }


def project_submission_source_metadata(submission) -> dict[str, Any]:
    project_url = project_public_url(submission.project)
    return {
        "github_link": submission.github_link,
        "commit_id": submission.commit_id,
        "faq_contribution_url": submission.faq_contribution_url or "",
        "project_url": project_url,
    }


def project_submission_status_metadata(submission) -> dict[str, Any]:
    return {
        "reviewed_enough_peers": submission.reviewed_enough_peers,
        "passed": submission.passed,
    }


def project_public_url(project):
    project_path = reverse(
        "project",
        kwargs={
            "course_slug": project.course.slug,
            "project_slug": project.slug,
        },
    )
    project_url = public_url(project_path)
    return project_url


def project_submission_recipient_list_payload(
    submission,
) -> RecipientListMemberPayload | None:
    email_value = submission.student.email or ""
    stripped_email = email_value.strip()
    email = stripped_email.lower()
    if not email:
        return None

    project = submission.project
    course = project.course
    list_key = project_submitters_list_key(project)
    source_object_key = f"project-submission:{submission.pk}"
    metadata = project_submission_metadata(submission)
    payload_data = RecipientListMemberPayloadData(
        list_type="project_submitters",
        list_name=f"{course.title} {project.title} submitters",
        email=email,
        source_object_key=source_object_key,
        metadata=metadata,
    )
    payload = recipient_list_member_payload(payload_data)
    if payload is None:
        return None
    return RecipientListMemberPayload(
        list_key=list_key,
        source_object_key=source_object_key,
        payload=payload,
    )
