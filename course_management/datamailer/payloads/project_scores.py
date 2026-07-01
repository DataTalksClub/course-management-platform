from typing import Any

from django.urls import reverse

from course_management import email_templates

from ..client import DatamailerConfig, public_url
from ..keys import project_submitters_list_key
from .score_members import project_score_notification_members
from .score_notifications import (
    add_from_email_if_configured,
    score_notification_footer,
)


def _project_score_notification_context(project):
    course = project.course
    urls = _project_score_notification_urls(course, project)
    project_results_url = urls["project_results_url"]
    profile_url = urls["profile_url"]
    footer = score_notification_footer(course, project, profile_url)
    context = {
        "course_slug": course.slug,
        "course_title": course.title,
        "project_slug": project.slug,
        "project_title": project.title,
        "course_url": urls["course_url"],
        "project_url": urls["project_url"],
        "project_results_url": project_results_url,
        "scores_url": project_results_url,
        "leaderboard_url": urls["leaderboard_url"],
        "profile_url": profile_url,
    }
    context.update(footer)
    return context


def _project_score_notification_urls(course, project):
    project_kwargs = {
        "course_slug": course.slug,
        "project_slug": project.slug,
    }
    course_path = reverse("course", kwargs={"course_slug": course.slug})
    course_url = public_url(course_path)

    project_path = reverse("project", kwargs=project_kwargs)
    project_url = public_url(project_path)

    project_results_path = reverse("project_results", kwargs=project_kwargs)
    project_results_url = public_url(project_results_path)

    leaderboard_path = reverse(
        "leaderboard",
        kwargs={"course_slug": course.slug},
    )
    leaderboard_url = public_url(leaderboard_path)

    profile_path = reverse("account_settings")
    profile_url = public_url(profile_path)

    return {
        "course_url": course_url,
        "project_url": project_url,
        "project_results_url": project_results_url,
        "leaderboard_url": leaderboard_url,
        "profile_url": profile_url,
    }


def _project_score_notification_metadata(project):
    return {
        "source": "course-management-platform",
        "event": "project_score_publication",
        "course_slug": project.course.slug,
        "project_slug": project.slug,
        "project_id": project.pk,
        "preference_key": "email_submission_confirmations",
        "cmp_preference_key": "email_submission_confirmations",
    }


def project_score_notification_payload(
    project,
) -> tuple[str, dict[str, Any]] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    course = project.course
    list_key = project_submitters_list_key(project)
    list_data, members = project_score_notification_members(project)
    context = _project_score_notification_context(project)
    metadata = _project_score_notification_metadata(project)
    payload = {
        "audience": config.audience,
        "client": config.client,
        "template_key": email_templates.PROJECT_SCORE_NOTIFICATION,
        "category_tag": "submission-results",
        "idempotency_key": f"project-score:{course.slug}:{project.slug}",
        "context": context,
        "list": list_data,
        "members": members,
        "metadata": metadata,
    }
    payload_with_from = add_from_email_if_configured(payload, config)
    return list_key, payload_with_from
