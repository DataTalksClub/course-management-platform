from typing import Any

from course_management import email_templates

from ..client import DatamailerConfig
from ..keys import homework_submitters_list_key
from .score_members import homework_score_notification_members
from .score_notifications import (
    add_from_email_if_configured,
    score_notification_footer,
    score_notification_urls,
)


def _homework_score_notification_context(homework):
    course = homework.course
    urls = score_notification_urls(
        course,
        homework,
        "homework",
        "homework_slug",
    )
    homework_url = urls["assignment_url"]
    footer = score_notification_footer(
        course,
        homework,
        urls["profile_url"],
    )
    context = {
        "course_slug": course.slug,
        "course_title": course.title,
        "homework_slug": homework.slug,
        "homework_title": homework.title,
        "course_url": urls["course_url"],
        "homework_url": homework_url,
        "scores_url": homework_url,
        "leaderboard_url": urls["leaderboard_url"],
        "profile_url": urls["profile_url"],
    }
    context.update(footer)
    return context


def _homework_score_notification_metadata(homework):
    return {
        "source": "course-management-platform",
        "event": "homework_score_publication",
        "course_slug": homework.course.slug,
        "homework_slug": homework.slug,
        "homework_id": homework.pk,
        "preference_key": "email_submission_confirmations",
        "cmp_preference_key": "email_submission_confirmations",
    }


def homework_score_notification_payload(
    homework,
) -> tuple[str, dict[str, Any]] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    course = homework.course
    list_key = homework_submitters_list_key(homework)
    list_data, members = homework_score_notification_members(homework)
    context = _homework_score_notification_context(homework)
    metadata = _homework_score_notification_metadata(homework)
    payload = {
        "audience": config.audience,
        "client": config.client,
        "template_key": email_templates.HOMEWORK_SCORE_NOTIFICATION,
        "category_tag": "submission-results",
        "idempotency_key": f"homework-score:{course.slug}:{homework.slug}",
        "context": context,
        "list": list_data,
        "members": members,
        "metadata": metadata,
    }
    payload_with_from = add_from_email_if_configured(payload, config)
    return list_key, payload_with_from
