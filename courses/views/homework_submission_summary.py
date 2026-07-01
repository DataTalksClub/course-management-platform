from dataclasses import dataclass
from typing import Any

from courses.models.course import Course
from courses.models.homework import Answer, Homework, Question, Submission
from courses.views.homework_answers import (
    CHOICE_QUESTION_TYPES,
    extract_selected_option_indexes,
    format_hours,
    format_selected_answer,
    selected_option_value,
)
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


def optional_homework_submission_fields(
    course: Course,
    homework: Homework,
    submission: Submission,
) -> list[dict[str, Any] | None]:
    fields = []
    homework_url_field = homework_url_submission_field(homework, submission)
    fields.append(homework_url_field)
    learning_in_public_field = learning_in_public_submission_field(
        homework,
        submission,
    )
    fields.append(learning_in_public_field)
    lecture_time_field = lecture_time_submission_field(homework, submission)
    fields.append(lecture_time_field)
    homework_time_field = homework_time_submission_field(homework, submission)
    fields.append(homework_time_field)
    problems_comments_field = problems_comments_submission_field(
        course,
        submission,
    )
    fields.append(problems_comments_field)
    faq_contribution_field = faq_contribution_submission_field(
        homework,
        submission,
    )
    fields.append(faq_contribution_field)
    return fields


def visible_homework_submission_fields(
    fields: list[dict[str, Any] | None],
) -> list[dict[str, Any]]:
    visible_fields = []
    for field in fields:
        if field is not None:
            visible_fields.append(field)
    return visible_fields


def homework_submission_fields(
    course: Course,
    homework: Homework,
    submission: Submission,
) -> list[dict[str, Any]]:
    fields = optional_homework_submission_fields(
        course,
        homework,
        submission,
    )
    return visible_homework_submission_fields(fields)


def homework_submitted_answers(
    submission: Submission,
) -> list[dict[str, Any]]:
    answer_payloads = []
    answers = submitted_homework_answers(submission)
    for answer in answers:
        payload = submitted_answer_payload(answer)
        answer_payloads.append(payload)
    return answer_payloads


def submitted_homework_answers(submission: Submission):
    return (
        Answer.objects.filter(submission=submission)
        .select_related("question")
        .order_by("question_id")
    )


def submitted_answer_payload(answer: Answer) -> dict[str, Any]:
    question = answer.question
    raw_answer = answer.answer_text or ""
    display_answer, selected_options = submitted_answer_display(
        question,
        raw_answer,
    )

    return {
        "question_id": question.id,
        "question": question.text,
        "question_type": question.question_type,
        "answer": display_answer,
        "raw_answer": raw_answer,
        "selected_options": selected_options,
    }


def submitted_answer_display(
    question: Question,
    raw_answer: str,
) -> tuple[str, list[dict[str, Any]]]:
    if question.question_type not in CHOICE_QUESTION_TYPES:
        return raw_answer, []

    selected_options = submitted_selected_options(question, raw_answer)
    display_answer = format_selected_answer(question, raw_answer)
    return display_answer, selected_options


def submitted_selected_options(
    question: Question,
    raw_answer: str,
) -> list[dict[str, Any]]:
    possible_answers = question.get_possible_answers()
    selected_options = []
    selected_indexes = extract_selected_option_indexes(raw_answer)
    for index in selected_indexes:
        selected_value = selected_option_value(possible_answers, index)
        option = {
            "index": index,
            "value": selected_value,
        }
        selected_options.append(option)
    return selected_options


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
