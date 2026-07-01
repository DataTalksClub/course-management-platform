from typing import Any

from django.urls import reverse

from course_management.deadlines import format_deadline_for_email

from ..client import public_url
from ..keys import project_submitters_list_key
from .base import (
    RecipientListMemberPayload,
    RecipientListMemberPayloadData,
    recipient_list_member_payload,
    recipient_list_send_member_payload,
)


def assigned_review_links(submission) -> list[dict[str, Any]]:
    project = submission.project
    course = project.course
    reviews = (
        submission.reviewers.filter(optional=False)
        .select_related("submission_under_evaluation")
        .order_by("id")
    )
    items = []
    for review in reviews:
        item = assigned_review_link_item(review, course, project)
        items.append(item)
    return items


def assigned_review_link_item(review, course, project) -> dict[str, Any]:
    target = review.submission_under_evaluation
    eval_url = assigned_review_eval_url(review, course, project)
    return {
        "review_id": review.id,
        "eval_url": eval_url,
        "submission_github_link": getattr(target, "github_link", "") or "",
    }


def assigned_review_eval_url(review, course, project) -> str:
    eval_path = reverse(
        "projects_eval_submit",
        kwargs={
            "course_slug": course.slug,
            "project_slug": project.slug,
            "review_id": review.id,
        },
    )
    eval_url = public_url(eval_path)
    return eval_url


def peer_review_assignment_metadata(submission) -> dict[str, Any]:
    identity_metadata = peer_review_assignment_identity_metadata(submission)
    review_metadata = peer_review_assignment_review_metadata(submission)
    deadline_metadata = peer_review_assignment_deadline_metadata(submission)
    return {
        **identity_metadata,
        **review_metadata,
        **deadline_metadata,
    }


def peer_review_assignment_identity_metadata(submission) -> dict[str, Any]:
    project = submission.project
    submitted_at = ""
    if submission.submitted_at:
        submitted_at = submission.submitted_at.isoformat()
    return {
        "submission_id": submission.pk,
        "user_id": submission.student_id,
        "course_slug": project.course.slug,
        "project_slug": project.slug,
        "submitted_at": submitted_at,
        "github_link": submission.github_link,
    }


def peer_review_assignment_review_metadata(submission) -> dict[str, Any]:
    project = submission.project
    reviews = assigned_review_links(submission)
    evaluations_url = peer_review_assignment_evaluations_url(project)
    return {
        "evaluations_url": evaluations_url,
        "number_of_peers_to_evaluate": project.number_of_peers_to_evaluate,
        "assigned_reviews": reviews,
        "assigned_reviews_count": len(reviews),
    }


def peer_review_assignment_evaluations_url(project) -> str:
    evaluations_path = reverse(
        "projects_eval",
        kwargs={
            "course_slug": project.course.slug,
            "project_slug": project.slug,
        },
    )
    evaluations_url = public_url(evaluations_path)
    return evaluations_url


def peer_review_assignment_deadline_metadata(
    submission,
) -> dict[str, Any]:
    project = submission.project
    deadline = format_deadline_for_email(
        project.peer_review_due_date,
        submission.student,
    )
    return {
        "deadline_weekday": deadline["deadline_weekday"],
        "deadline_date": deadline["deadline_date"],
        "deadline_time": deadline["deadline_time"],
        "deadline_timezone": deadline["deadline_timezone"],
        "deadline_summary": deadline["deadline_summary"],
    }


def peer_review_assignment_recipient_list_payload(
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
    metadata = peer_review_assignment_metadata(submission)
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


def peer_review_assignment_notification_members(
    project,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    list_data = peer_review_assignment_list_data(project)
    members = []
    seen_students = set()
    submissions = peer_review_assignment_submissions(project)
    for submission in submissions:
        if submission.student_id in seen_students:
            continue
        item = peer_review_assignment_recipient_list_payload(submission)
        if item is None:
            continue
        seen_students.add(submission.student_id)
        member_payload = item.payload
        list_data = item.payload["list"]
        member = recipient_list_send_member_payload(
            item.source_object_key, member_payload
        )
        members.append(member)
    return list_data, members


def peer_review_assignment_list_data(project) -> dict[str, Any]:
    return {
        "type": "project_submitters",
        "name": f"{project.course.title} {project.title} submitters",
        "metadata": {
            "course_slug": project.course.slug,
            "project_slug": project.slug,
        },
    }


def peer_review_assignment_submissions(project):
    return project.projectsubmission_set.select_related(
        "student", "project__course"
    ).order_by("student_id", "-submitted_at", "-id")
