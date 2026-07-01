from typing import Any

from django.urls import reverse

from course_management import email_templates

from ..client import DatamailerConfig, public_url
from ..keys import (
    homework_submitters_list_key,
    project_submitters_list_key,
)
from .base import (
    recipient_list_send_member_payload,
)
from .submissions import (
    homework_submission_recipient_list_payload,
    project_submission_recipient_list_payload,
)

def homework_score_notification_members(
    homework,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    list_data = homework_score_notification_list_data(homework)
    members = []
    seen_students = set()
    submissions = homework_score_notification_submissions(homework)
    for submission in submissions:
        if submission.student_id in seen_students:
            continue
        item = homework_submission_recipient_list_payload(submission)
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


def homework_score_notification_list_data(homework) -> dict[str, Any]:
    return {
        "type": "homework_submitters",
        "name": f"{homework.course.title} {homework.title} submitters",
        "metadata": {
            "course_slug": homework.course.slug,
            "homework_slug": homework.slug,
        },
    }


def homework_score_notification_submissions(homework):
    return homework.submission_set.select_related(
        "student", "homework__course"
    ).order_by("student_id", "-submitted_at", "-id")


def project_score_notification_members(
    project,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    list_data = project_score_notification_list_data(project)
    members = []
    seen_students = set()
    submissions = project_score_notification_submissions(project)
    for submission in submissions:
        if submission.student_id in seen_students:
            continue
        item = project_submission_recipient_list_payload(submission)
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


def project_score_notification_list_data(project) -> dict[str, Any]:
    return {
        "type": "project_submitters",
        "name": f"{project.course.title} {project.title} submitters",
        "metadata": {
            "course_slug": project.course.slug,
            "project_slug": project.slug,
        },
    }


def project_score_notification_submissions(project):
    return project.projectsubmission_set.select_related(
        "student", "project__course"
    ).order_by("student_id", "-submitted_at", "-id")


def _score_notification_urls(course, assignment, route_name, slug_kwarg):
    assignment_path = reverse(
        route_name,
        kwargs={
            "course_slug": course.slug,
            slug_kwarg: assignment.slug,
        },
    )
    assignment_url = public_url(assignment_path)

    course_path = reverse("course", kwargs={"course_slug": course.slug})
    course_url = public_url(course_path)

    leaderboard_path = reverse("leaderboard", kwargs={"course_slug": course.slug})
    leaderboard_url = public_url(leaderboard_path)

    profile_path = reverse("account_settings")
    profile_url = public_url(profile_path)

    return {
        "course_url": course_url,
        "assignment_url": assignment_url,
        "leaderboard_url": leaderboard_url,
        "profile_url": profile_url,
    }


def _score_notification_footer(course, assignment, profile_url):
    return {
        "notification_footer": (
            f"You are receiving this because you submitted {assignment.title} "
            f"for {course.title} and homework/project submission emails "
            "are enabled in your profile."
        ),
        "notification_footer_text": (
            "If you don't want to receive homework/project submission "
            "and score emails, turn off homework and project submission "
            f"emails in your profile: {profile_url}"
        ),
    }


def _homework_score_notification_context(homework):
    course = homework.course
    urls = _score_notification_urls(
        course,
        homework,
        "homework",
        "homework_slug",
    )
    homework_url = urls["assignment_url"]
    return {
        "course_slug": course.slug,
        "course_title": course.title,
        "homework_slug": homework.slug,
        "homework_title": homework.title,
        "course_url": urls["course_url"],
        "homework_url": homework_url,
        "scores_url": homework_url,
        "leaderboard_url": urls["leaderboard_url"],
        "profile_url": urls["profile_url"],
        **_score_notification_footer(course, homework, urls["profile_url"]),
    }


def _project_score_notification_context(project):
    course = project.course
    urls = _project_score_notification_urls(course, project)
    project_results_url = urls["project_results_url"]
    profile_url = urls["profile_url"]
    return {
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
        **_score_notification_footer(course, project, profile_url),
    }


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

    leaderboard_path = reverse("leaderboard", kwargs={"course_slug": course.slug})
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


def homework_score_notification_payload(
    homework,
) -> tuple[str, dict[str, Any]] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    course = homework.course
    list_key = homework_submitters_list_key(homework)
    list_data, members = homework_score_notification_members(homework)
    payload = {
        "audience": config.audience,
        "client": config.client,
        "template_key": email_templates.HOMEWORK_SCORE_NOTIFICATION,
        "category_tag": "submission-results",
        "idempotency_key": f"homework-score:{course.slug}:{homework.slug}",
        "context": _homework_score_notification_context(homework),
        "list": list_data,
        "members": members,
        "metadata": _homework_score_notification_metadata(homework),
    }
    if config.from_email:
        payload["from_email"] = config.from_email
    return list_key, payload

def project_score_notification_payload(
    project,
) -> tuple[str, dict[str, Any]] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    course = project.course
    list_key = project_submitters_list_key(project)
    list_data, members = project_score_notification_members(project)
    payload = {
        "audience": config.audience,
        "client": config.client,
        "template_key": email_templates.PROJECT_SCORE_NOTIFICATION,
        "category_tag": "submission-results",
        "idempotency_key": f"project-score:{course.slug}:{project.slug}",
        "context": _project_score_notification_context(project),
        "list": list_data,
        "members": members,
        "metadata": _project_score_notification_metadata(project),
    }
    if config.from_email:
        payload["from_email"] = config.from_email
    return list_key, payload
