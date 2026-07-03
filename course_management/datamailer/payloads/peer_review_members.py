from typing import Any

from django.db.models import Prefetch

from accounts.services.timezones import format_deadline_for_user
from courses.models.project import PeerReview

from ..keys import project_submitters_list_key
from .base import (
    RecipientListMemberPayload,
    RecipientListMemberPayloadData,
    normalized_email,
    recipient_list_member_payload,
    recipient_list_send_member_payload,
)
from .urls import public_route_url


ASSIGNED_REVIEWS_ATTR = "assigned_reviews"


def _assigned_reviews(submission):
    prefetched = getattr(submission, ASSIGNED_REVIEWS_ATTR, None)
    if prefetched is not None:
        return prefetched
    return (
        submission.reviewers.filter(optional=False)
        .select_related("submission_under_evaluation")
        .order_by("id")
    )


def assigned_reviews_prefetch() -> Prefetch:
    return Prefetch(
        "reviewers",
        queryset=PeerReview.objects.filter(optional=False)
        .select_related("submission_under_evaluation")
        .order_by("id"),
        to_attr=ASSIGNED_REVIEWS_ATTR,
    )


def assigned_review_links(submission) -> list[dict[str, Any]]:
    project = submission.project
    course = project.course
    reviews = _assigned_reviews(submission)
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
    eval_kwargs = {
        "course_slug": course.slug,
        "project_slug": project.slug,
        "review_id": review.id,
    }
    eval_url = public_route_url("projects_eval_submit", eval_kwargs)
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
    assigned_reviews_count = len(reviews)
    evaluations_url = peer_review_assignment_evaluations_url(project)
    return {
        "evaluations_url": evaluations_url,
        "number_of_peers_to_evaluate": project.number_of_peers_to_evaluate,
        "assigned_reviews": reviews,
        "assigned_reviews_count": assigned_reviews_count,
    }


def peer_review_assignment_evaluations_url(project) -> str:
    evaluations_kwargs = {
        "course_slug": project.course.slug,
        "project_slug": project.slug,
    }
    evaluations_url = public_route_url("projects_eval", evaluations_kwargs)
    return evaluations_url


def peer_review_assignment_deadline_metadata(
    submission,
) -> dict[str, Any]:
    project = submission.project
    deadline = format_deadline_for_user(
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
    email = normalized_email(submission.student.email)
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
    submissions = (
        project.projectsubmission_set.select_related(
            "student", "project__course"
        )
        .prefetch_related(assigned_reviews_prefetch())
        .order_by("student_id", "-submitted_at", "-id")
    )
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
