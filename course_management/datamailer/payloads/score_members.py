from typing import Any

from .base import recipient_list_send_member_payload
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
    submissions = homework.submission_set.select_related(
        "student", "homework__course"
    ).order_by("student_id", "-submitted_at", "-id")
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


def project_score_notification_members(
    project,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    list_data = project_score_notification_list_data(project)
    members = []
    seen_students = set()
    submissions = project.projectsubmission_set.select_related(
        "student", "project__course"
    ).order_by("student_id", "-submitted_at", "-id")
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
