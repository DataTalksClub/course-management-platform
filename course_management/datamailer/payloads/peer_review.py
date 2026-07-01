from typing import Any

from django.urls import reverse

from course_management import email_templates
from course_management.deadlines import format_deadline_for_email

from ..client import DatamailerConfig, public_url
from ..keys import project_submitters_list_key
from .base import (
    RecipientListMemberPayload,
    RecipientListMemberPayloadData,
    recipient_list_member_payload,
    recipient_list_send_member_payload,
)

def _assigned_review_links(submission) -> list[dict[str, Any]]:
    """The non-optional peer reviews this submission's author must complete,
    each with a direct evaluation link and the target's GitHub link."""
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
    return {
        "review_id": review.id,
        "eval_url": assigned_review_eval_url(review, course, project),
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
    return {
        **peer_review_assignment_identity_metadata(submission),
        **peer_review_assignment_review_metadata(submission),
        **peer_review_assignment_deadline_metadata(submission),
    }


def peer_review_assignment_identity_metadata(submission) -> dict[str, Any]:
    project = submission.project
    return {
        "submission_id": submission.pk,
        "user_id": submission.student_id,
        "course_slug": project.course.slug,
        "project_slug": project.slug,
        "submitted_at": submission.submitted_at.isoformat()
        if submission.submitted_at
        else "",
        "github_link": submission.github_link,
    }


def peer_review_assignment_review_metadata(submission) -> dict[str, Any]:
    project = submission.project
    assigned_reviews = _assigned_review_links(submission)
    return {
        "evaluations_url": peer_review_assignment_evaluations_url(project),
        "number_of_peers_to_evaluate": project.number_of_peers_to_evaluate,
        "assigned_reviews": assigned_reviews,
        "assigned_reviews_count": len(assigned_reviews),
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
    payload_data = RecipientListMemberPayloadData(
        list_type="project_submitters",
        list_name=f"{course.title} {project.title} submitters",
        email=email,
        source_object_key=source_object_key,
        metadata=peer_review_assignment_metadata(submission),
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


def public_route_url(route_name, route_kwargs=None):
    if route_kwargs is None:
        path = reverse(route_name)
    else:
        path = reverse(route_name, kwargs=route_kwargs)
    url = public_url(path)
    return url


def _peer_review_assignment_urls(course, project) -> dict[str, str]:
    course_kwargs = {"course_slug": course.slug}
    project_kwargs = {
        "course_slug": course.slug,
        "project_slug": project.slug,
    }
    course_url = public_route_url("course", course_kwargs)
    project_url = public_route_url("project", project_kwargs)
    evaluations_url = public_route_url("projects_eval", project_kwargs)
    leaderboard_url = public_route_url("leaderboard", course_kwargs)
    profile_url = public_route_url("account_settings")

    return {
        "course_url": course_url,
        "project_url": project_url,
        "evaluations_url": evaluations_url,
        "leaderboard_url": leaderboard_url,
        "profile_url": profile_url,
    }


def _peer_review_assignment_context(course, project) -> dict[str, Any]:
    urls = _peer_review_assignment_urls(course, project)
    return {
        **_peer_review_assignment_project_context(course, project),
        **urls,
        **_peer_review_assignment_deadline_context(project),
        **_peer_review_assignment_message_context(course, project, urls),
    }


def _peer_review_assignment_project_context(course, project) -> dict[str, Any]:
    return {
        "course_slug": course.slug,
        "course_title": course.title,
        "project_slug": project.slug,
        "project_title": project.title,
        "number_of_peers_to_evaluate": project.number_of_peers_to_evaluate,
    }


def _peer_review_assignment_deadline_context(project) -> dict[str, Any]:
    deadline = format_deadline_for_email(project.peer_review_due_date)
    return {
        "peer_review_due_at": project.peer_review_due_date.isoformat(),
        "deadline_weekday": deadline["deadline_weekday"],
        "deadline_date": deadline["deadline_date"],
        "deadline_time": deadline["deadline_time"],
        "deadline_summary": deadline["deadline_summary"],
    }


def _peer_review_assignment_message_context(
    course,
    project,
    urls,
) -> dict[str, Any]:
    num_peers = project.number_of_peers_to_evaluate
    return {
        "email_subject": f"Peer review is open: {project.title}",
        "email_preview": (
            f"Time to evaluate {num_peers} projects for {project.title}."
        ),
        "intro_text": (
            f"Thanks for submitting {project.title} in {course.title}. "
            f"Peer review is now open - you have {num_peers} projects to "
            "evaluate before the deadline."
        ),
        "notification_footer": (
            f"You are receiving this because you submitted {project.title} "
            f"for {course.title} and homework/project submission emails "
            "are enabled in your profile."
        ),
        "notification_footer_text": (
            "If you don't want to receive homework/project submission "
            "and score emails, turn off homework and project submission "
            f"emails in your profile: {urls['profile_url']}"
        ),
    }


def _peer_review_assignment_metadata(course, project) -> dict[str, Any]:
    return {
        "source": "course-management-platform",
        "event": "peer_review_assignment",
        "course_slug": course.slug,
        "project_slug": project.slug,
        "project_id": project.pk,
        "preference_key": "email_submission_confirmations",
        "cmp_preference_key": "email_submission_confirmations",
    }


def peer_review_assignment_notification_payload(
    project,
) -> tuple[str, dict[str, Any]] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    course = project.course
    list_key = project_submitters_list_key(project)
    list_data, members = peer_review_assignment_notification_members(project)
    context = _peer_review_assignment_context(course, project)
    metadata = _peer_review_assignment_metadata(course, project)

    payload = {
        "audience": config.audience,
        "client": config.client,
        "template_key": email_templates.PEER_REVIEW_ASSIGNMENT,
        "category_tag": "submission-results",
        "idempotency_key": (
            f"peer-review-assignment:{course.slug}:{project.slug}"
        ),
        "context": context,
        "list": list_data,
        "members": members,
        "metadata": metadata,
    }
    if config.from_email:
        payload["from_email"] = config.from_email
    return list_key, payload
