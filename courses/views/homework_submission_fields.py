from dataclasses import dataclass

from django.core.exceptions import ValidationError
from django.http import HttpRequest

from courses.models.course import Course, User
from courses.models.homework import Homework, Submission
from courses.validators.custom_url_validators import (
    clean_faq_contribution_url,
)
from courses.views.homework_learning_links import (
    clean_learning_in_public_links,
    find_duplicate_learning_in_public_links,
)
from courses.views.submission_formatting import parse_time_spent_hours


@dataclass(frozen=True)
class HomeworkSubmissionFieldData:
    submission: Submission
    request: HttpRequest
    course: Course
    homework: Homework
    user: User


@dataclass(frozen=True)
class HomeworkTimeSpentFieldData:
    submission: Submission
    request: HttpRequest
    enabled: bool
    post_key: str
    model_field: str
    field_label: str


def apply_homework_submission_fields(field_data):
    if field_data.homework.homework_url_field:
        field_data.submission.homework_link = (
            field_data.request.POST.get("homework_url")
        )
    apply_learning_in_public_links(field_data)
    apply_time_spent_fields(field_data)
    if field_data.course.homework_problems_comments_field:
        field_data.submission.problems_comments = (
            field_data.request.POST.get(
                "problems_comments",
                "",
            ).strip()
        )
    apply_faq_contribution_field(field_data)


def apply_learning_in_public_links(field_data):
    if field_data.homework.learning_in_public_cap <= 0:
        return

    links = field_data.request.POST.getlist(
        "learning_in_public_links[]"
    )
    cleaned_links = clean_learning_in_public_links(
        links,
        field_data.homework.learning_in_public_cap,
    )
    duplicate_links = find_duplicate_learning_in_public_links(
        user=field_data.user,
        course=field_data.course,
        links=cleaned_links,
        current_submission=field_data.submission,
    )
    if duplicate_links:
        raise ValidationError(
            "Learning in public links were already used in another "
            f"submission: {', '.join(duplicate_links)}"
        )
    field_data.submission.learning_in_public_links = cleaned_links


def apply_time_spent_fields(field_data):
    lectures_field_data = HomeworkTimeSpentFieldData(
        submission=field_data.submission,
        request=field_data.request,
        enabled=field_data.homework.time_spent_lectures_field,
        post_key="time_spent_lectures",
        model_field="time_spent_lectures",
        field_label="time spent on lectures",
    )
    apply_time_spent_field(lectures_field_data)

    homework_field_data = HomeworkTimeSpentFieldData(
        submission=field_data.submission,
        request=field_data.request,
        enabled=field_data.homework.time_spent_homework_field,
        post_key="time_spent_homework",
        model_field="time_spent_homework",
        field_label="time spent on homework",
    )
    apply_time_spent_field(homework_field_data)


def apply_time_spent_field(data):
    if not data.enabled:
        return

    posted_time_spent = data.request.POST.get(data.post_key)
    time_spent = parse_time_spent_hours(
        posted_time_spent,
        data.field_label,
    )
    if time_spent is not None:
        setattr(data.submission, data.model_field, time_spent)


def apply_faq_contribution_field(field_data):
    if field_data.homework.faq_contribution_field:
        posted_url = field_data.request.POST.get("faq_contribution_url", "")
        faq_contribution_url = clean_faq_contribution_url(posted_url)
        field_data.submission.faq_contribution_url = (
            faq_contribution_url.strip()
        )
