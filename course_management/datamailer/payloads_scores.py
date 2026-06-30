from typing import Any

from django.urls import reverse

from course_management import email_templates

from .client import DatamailerConfig, public_url
from .keys import (
    homework_submitters_list_key,
    project_passed_list_key,
    project_submitters_list_key,
)
from .payloads_base import (
    RecipientListMemberPayload,
    homework_submission_recipient_list_payload,
    project_submission_recipient_list_payload,
    recipient_list_send_member_payload,
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


def project_passed_recipient_list_payload(
    project,
) -> tuple[str, dict[str, Any]] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    list_key = project_passed_list_key(project)
    payload = _bulk_recipient_list_payload(
        config,
        _project_passed_list_data(project),
        _project_passed_members(project),
    )
    return list_key, payload


def _project_passed_list_data(project) -> dict[str, Any]:
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


def _project_passed_members(project) -> list[dict[str, Any]]:
    members = []
    seen_students = set()
    candidate_submissions = _project_passed_candidate_submissions(project)
    for submission in candidate_submissions:
        if submission.student_id in seen_students:
            continue
        seen_students.add(submission.student_id)
        member = _project_passed_member(submission)
        if member is not None:
            members.append(member)
    return members


def _project_passed_candidate_submissions(project):
    return project.projectsubmission_set.select_related(
        "student", "project__course"
    ).order_by("student_id", "-submitted_at", "-id")


def _project_passed_member(submission) -> dict[str, Any] | None:
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


def _bulk_recipient_list_payload(config, list_data, members):
    return {
        "audience": config.audience,
        "client": config.client,
        "list": list_data,
        "members": members,
    }


def _project_passed_member_payload(project, payload) -> dict[str, Any]:
    return {
        **payload,
        "list": _project_passed_list_data(project),
        "member": _project_passed_member_payload_data(payload),
    }


def _project_passed_member_payload_data(payload) -> dict[str, Any]:
    return {
        **payload["member"],
        "metadata": _project_passed_member_metadata(payload),
    }


def _project_passed_member_metadata(payload) -> dict[str, Any]:
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
    member_payload = _project_passed_member_payload(project, payload)
    return RecipientListMemberPayload(
        list_key=project_passed_list_key(project),
        source_object_key=item.source_object_key,
        payload=member_payload,
    )


def _score_notification_urls(course, assignment, route_name, slug_kwarg):
    assignment_url = public_url(
        reverse(
            route_name,
            kwargs={
                "course_slug": course.slug,
                slug_kwarg: assignment.slug,
            },
        )
    )
    return {
        "course_url": public_url(
            reverse("course", kwargs={"course_slug": course.slug})
        ),
        "assignment_url": assignment_url,
        "leaderboard_url": public_url(
            reverse("leaderboard", kwargs={"course_slug": course.slug})
        ),
        "profile_url": public_url(reverse("account_settings")),
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
    return {
        "course_url": public_url(
            reverse("course", kwargs={"course_slug": course.slug})
        ),
        "project_url": public_url(
            reverse("project", kwargs=project_kwargs)
        ),
        "project_results_url": public_url(
            reverse("project_results", kwargs=project_kwargs)
        ),
        "leaderboard_url": public_url(
            reverse("leaderboard", kwargs={"course_slug": course.slug})
        ),
        "profile_url": public_url(reverse("account_settings")),
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
