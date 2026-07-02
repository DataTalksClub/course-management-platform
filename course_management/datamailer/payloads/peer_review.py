from typing import Any

from course_management import email_templates
from accounts.services.timezones import format_deadline_for_user

from ..client import DatamailerConfig
from ..keys import project_submitters_list_key
from .peer_review_members import (
    peer_review_assignment_notification_members,
)
from .score_notifications import add_from_email_if_configured
from .urls import public_route_url


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
    project_context = _peer_review_assignment_project_context(course, project)
    deadline_context = _peer_review_assignment_deadline_context(project)
    message_context = _peer_review_assignment_message_context(
        course,
        project,
        urls,
    )
    return {
        **project_context,
        **urls,
        **deadline_context,
        **message_context,
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
    deadline = format_deadline_for_user(project.peer_review_due_date)
    peer_review_due_at = project.peer_review_due_date.isoformat()
    return {
        "peer_review_due_at": peer_review_due_at,
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


def _peer_review_assignment_delivery_fields(
    config,
    course,
    project,
) -> dict[str, Any]:
    idempotency_key = (
        f"peer-review-assignment:{course.slug}:{project.slug}"
    )
    return {
        "audience": config.audience,
        "client": config.client,
        "template_key": email_templates.PEER_REVIEW_ASSIGNMENT,
        "category_tag": "submission-results",
        "idempotency_key": idempotency_key,
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

    payload = _peer_review_assignment_delivery_fields(
        config,
        course,
        project,
    )
    payload["context"] = context
    payload["list"] = list_data
    payload["members"] = members
    payload["metadata"] = metadata
    payload_with_from = add_from_email_if_configured(payload, config)
    return list_key, payload_with_from
