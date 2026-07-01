from dataclasses import dataclass
from typing import Any

from courses.models.course import Course
from courses.models.homework import Homework, Submission
from courses.views.homework_answer_formatting import format_hours
from courses.views.homework_submission_answers import homework_submitted_answers
from courses.views.submission_formatting import (
    format_answer_lines,
    format_submission_lines,
    submission_summary_text,
)


@dataclass(frozen=True)
class HomeworkSubmittedContent:
    fields: list[dict[str, Any]]
    answers: list[dict[str, Any]]
    fields_text: str
    answers_text: str
    summary_text: str

    def context(self) -> dict[str, Any]:
        return {
            "submission_fields": self.fields,
            "submitted_answers": self.answers,
            "submitted_fields_text": self.fields_text,
            "submitted_answers_text": self.answers_text,
            "submission_summary_text": self.summary_text,
        }


def homework_url_submission_field(
    homework: Homework,
    submission: Submission,
) -> dict[str, Any] | None:
    if not homework.homework_url_field:
        return None

    return {
        "key": "homework_url",
        "label": "Homework URL",
        "value": submission.homework_link or "",
    }


def learning_in_public_submission_field(
    homework: Homework,
    submission: Submission,
) -> dict[str, Any] | None:
    if homework.learning_in_public_cap <= 0:
        return None

    links = submission.learning_in_public_links or []
    value = "\n".join(links)
    return {
        "key": "learning_in_public_links",
        "label": "Learning in public links",
        "value": value,
        "values": links,
    }


def lecture_time_submission_field(
    homework: Homework,
    submission: Submission,
) -> dict[str, Any] | None:
    if not homework.time_spent_lectures_field:
        return None

    value = format_hours(submission.time_spent_lectures)
    return {
        "key": "time_spent_lectures",
        "label": "Time spent on lectures",
        "value": value,
    }


def homework_time_submission_field(
    homework: Homework,
    submission: Submission,
) -> dict[str, Any] | None:
    if not homework.time_spent_homework_field:
        return None

    value = format_hours(submission.time_spent_homework)
    return {
        "key": "time_spent_homework",
        "label": "Time spent on homework",
        "value": value,
    }


def problems_comments_submission_field(
    course: Course,
    submission: Submission,
) -> dict[str, Any] | None:
    if not course.homework_problems_comments_field:
        return None

    return {
        "key": "problems_comments",
        "label": "Problems, comments, or feedback",
        "value": submission.problems_comments or "",
    }


def faq_contribution_submission_field(
    homework: Homework,
    submission: Submission,
) -> dict[str, Any] | None:
    if not homework.faq_contribution_field:
        return None

    return {
        "key": "faq_contribution_url",
        "label": "FAQ contribution URL",
        "value": submission.faq_contribution_url or "",
    }


def add_visible_submission_field(
    fields: list[dict[str, Any]],
    field: dict[str, Any] | None,
) -> None:
    if field is None:
        return

    fields.append(field)


def add_homework_detail_submission_fields(
    fields: list[dict[str, Any]],
    homework: Homework,
    submission: Submission,
) -> None:
    homework_url_field = homework_url_submission_field(homework, submission)
    add_visible_submission_field(fields, homework_url_field)
    learning_in_public_field = learning_in_public_submission_field(
        homework,
        submission,
    )
    add_visible_submission_field(fields, learning_in_public_field)
    lecture_time_field = lecture_time_submission_field(homework, submission)
    add_visible_submission_field(fields, lecture_time_field)
    homework_time_field = homework_time_submission_field(homework, submission)
    add_visible_submission_field(fields, homework_time_field)


def add_course_owned_submission_fields(
    fields: list[dict[str, Any]],
    course: Course,
    submission: Submission,
) -> None:
    problems_comments_field = problems_comments_submission_field(
        course,
        submission,
    )
    add_visible_submission_field(fields, problems_comments_field)


def homework_submission_fields(
    course: Course,
    homework: Homework,
    submission: Submission,
) -> list[dict[str, Any]]:
    fields = []
    add_homework_detail_submission_fields(fields, homework, submission)
    add_course_owned_submission_fields(fields, course, submission)
    faq_contribution_field = faq_contribution_submission_field(
        homework,
        submission,
    )
    add_visible_submission_field(fields, faq_contribution_field)
    return fields


def homework_submitted_content(
    course: Course,
    homework: Homework,
    submission: Submission,
) -> HomeworkSubmittedContent:
    submission_fields = homework_submission_fields(
        course,
        homework,
        submission,
    )
    submitted_answers = homework_submitted_answers(submission)
    submitted_fields_text = format_submission_lines(submission_fields)
    submitted_answers_text = format_answer_lines(submitted_answers)
    summary_text = submission_summary_text(
        submitted_fields_text,
        submitted_answers_text,
    )

    return HomeworkSubmittedContent(
        fields=submission_fields,
        answers=submitted_answers,
        fields_text=submitted_fields_text,
        answers_text=submitted_answers_text,
        summary_text=summary_text,
    )
