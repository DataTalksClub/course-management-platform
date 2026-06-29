import logging

from dataclasses import dataclass
from typing import Any, List, Optional
from urllib.parse import urljoin, urlparse

from django.http import HttpRequest

from django.contrib import messages
from django.utils import timezone
from django.shortcuts import render, get_object_or_404, redirect
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import transaction
from django.urls import reverse

from course_management.datamailer import (
    send_transactional_email,
    sync_homework_submission_to_datamailer,
)
from course_management import email_templates
from courses.models import (
    Course,
    Homework,
    HomeworkState,
    Question,
    Answer,
    Submission,
    QuestionTypes,
    Enrollment,
    User,
    ProjectSubmission,
)

from courses.scoring import (
    is_free_form_answer_correct,
    calculate_homework_statistics,
)
from courses.validators import clean_faq_contribution_url
from courses.views.url_utils import absolute_url_with_fallback

logger = logging.getLogger(__name__)


NONE_LIST = [None]
CHOICE_QUESTION_TYPES = {
    QuestionTypes.MULTIPLE_CHOICE.value,
    QuestionTypes.CHECKBOXES.value,
}
FREE_FORM_QUESTION_TYPES = {
    QuestionTypes.FREE_FORM.value,
    QuestionTypes.FREE_FORM_LONG.value,
}


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


@dataclass(frozen=True)
class HomeworkPostData:
    request: HttpRequest
    course: Course
    homework: Homework
    questions: List[Question]
    submission: Optional[Submission]
    enrollment: Enrollment


@dataclass(frozen=True)
class HomeworkConfirmationData:
    course: Course
    homework: Homework
    submission: Submission
    update_url: str
    profile_url: str


@dataclass(frozen=True)
class ChoiceOptionData:
    homework: Homework
    option: str
    index: int
    selected_options: list[int]
    correct_indices: list[int]


@dataclass(frozen=True)
class HomeworkSubmissionFieldData:
    submission: Submission
    request: HttpRequest
    course: Course
    homework: Homework
    user: User


def process_unscored_free_form_answer(answer: Optional[Answer]):
    if not answer:
        return {"text": ""}

    return {"text": answer.answer_text}


def free_form_answer_missing(answer: Optional[Answer]) -> bool:
    return (
        not answer
        or not answer.answer_text
        or not answer.answer_text.strip()
    )


def process_missing_scored_free_form_answer(question: Question):
    return {
        "text": question.correct_answer,
        "no_answer_submitted": True,
    }


def free_form_answer_class(is_correct: bool) -> str:
    if is_correct:
        return "option-answer-correct"

    return "option-answer-incorrect"


def process_scored_free_form_answer(
    question: Question, answer: Optional[Answer]
):
    if free_form_answer_missing(answer):
        return process_missing_scored_free_form_answer(question)

    return {
        "text": answer.answer_text,
        "correctly_selected_class": free_form_answer_class(
            is_free_form_answer_correct(question, answer)
        ),
    }


def process_question_free_form(
    homework: Homework, question: Question, answer: Optional[Answer]
):
    if not homework.is_scored():
        return process_unscored_free_form_answer(answer)

    return process_scored_free_form_answer(question, answer)


def process_question_options_multiple_choice_or_checkboxes(
    homework: Homework, question: Question, answer: Optional[Answer]
):
    selected_options = extract_selected_options(answer)
    possible_answers = question.get_possible_answers()
    correct_indices = (
        question.get_correct_answer_indices()
        if homework.is_scored()
        else []
    )

    options = []
    for index, option in enumerate(possible_answers, start=1):
        option_data = ChoiceOptionData(
            homework=homework,
            option=option,
            index=index,
            selected_options=selected_options,
            correct_indices=correct_indices,
        )
        processed_option = process_choice_option(option_data)
        options.append(processed_option)

    result = {"options": options}
    if no_choice_answer_submitted(homework, selected_options):
        result["no_answer_submitted"] = True

    return result


def process_choice_option(data: ChoiceOptionData):
    is_selected = data.index in data.selected_options
    processed_answer = {
        "value": data.option,
        "is_selected": is_selected,
        "index": data.index,
    }

    if data.homework.state == HomeworkState.SCORED.value:
        is_correct = data.index in data.correct_indices
        processed_answer.update(
            {
                "is_correct": is_correct,
                "correctly_selected_class": determine_answer_class(
                    is_selected, is_correct
                ),
            }
        )

    return processed_answer


def no_choice_answer_submitted(
    homework: Homework,
    selected_options: list[int],
) -> bool:
    return homework.is_scored() and len(selected_options) == 0


def extract_selected_options(answer):
    if not answer:
        return []

    return extract_selected_option_indexes(answer.answer_text)


def _selected_option_index(option: str) -> Optional[int]:
    option = option.strip()
    if not option:
        return None

    try:
        return int(option)
    except ValueError:
        return None


def _selected_option_indexes(answer_text: Optional[str]):
    options = (answer_text or "").strip().split(",")
    for option in options:
        index = _selected_option_index(option)
        if index is not None:
            yield index


def extract_selected_option_indexes(
    answer_text: Optional[str],
) -> List[int]:
    indexes = []
    selected_option_indexes = _selected_option_indexes(answer_text)
    for index in selected_option_indexes:
        indexes.append(index)
    return indexes


def format_hours(value: Optional[float]) -> str:
    if value is None:
        return ""

    return f"{value:g} hours"


def format_submitted_value(value: str) -> str:
    return value if value else "Not submitted"


def format_selected_answer(
    question: Question,
    answer_text: Optional[str],
) -> str:
    selected_indexes = extract_selected_option_indexes(answer_text)
    possible_answers = question.get_possible_answers()
    selected_options = []
    for index in selected_indexes:
        option = selected_option_label(possible_answers, index)
        selected_options.append(option)
    return ", ".join(selected_options)


def selected_option_value(
    possible_answers: List[str],
    index: int,
) -> str:
    if 1 <= index <= len(possible_answers):
        return possible_answers[index - 1]
    return ""


def selected_option_label(
    possible_answers: List[str],
    index: int,
) -> str:
    value = selected_option_value(possible_answers, index)
    if value:
        return f"{index}. {value}"
    return str(index)


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
    return {
        "key": "learning_in_public_links",
        "label": "Learning in public links",
        "value": "\n".join(links),
        "values": links,
    }


def lecture_time_submission_field(
    homework: Homework,
    submission: Submission,
) -> dict[str, Any] | None:
    if not homework.time_spent_lectures_field:
        return None

    return {
        "key": "time_spent_lectures",
        "label": "Time spent on lectures",
        "value": format_hours(submission.time_spent_lectures),
    }


def homework_time_submission_field(
    homework: Homework,
    submission: Submission,
) -> dict[str, Any] | None:
    if not homework.time_spent_homework_field:
        return None

    return {
        "key": "time_spent_homework",
        "label": "Time spent on homework",
        "value": format_hours(submission.time_spent_homework),
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
) -> List[dict[str, Any] | None]:
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
    fields: List[dict[str, Any] | None],
) -> List[dict[str, Any]]:
    visible_fields = []
    for field in fields:
        if field is not None:
            visible_fields.append(field)
    return visible_fields


def homework_submission_fields(
    course: Course,
    homework: Homework,
    submission: Submission,
) -> List[dict[str, Any]]:
    fields = optional_homework_submission_fields(
        course,
        homework,
        submission,
    )
    return visible_homework_submission_fields(fields)


def homework_submitted_answers(
    submission: Submission,
) -> List[dict[str, Any]]:
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
) -> tuple[str, List[dict[str, Any]]]:
    if question.question_type not in CHOICE_QUESTION_TYPES:
        return raw_answer, []

    selected_options = submitted_selected_options(question, raw_answer)
    display_answer = format_selected_answer(question, raw_answer)
    return display_answer, selected_options


def submitted_selected_options(
    question: Question,
    raw_answer: str,
) -> List[dict[str, Any]]:
    possible_answers = question.get_possible_answers()
    selected_options = []
    selected_indexes = extract_selected_option_indexes(raw_answer)
    for index in selected_indexes:
        option = {
            "index": index,
            "value": selected_option_value(possible_answers, index),
        }
        selected_options.append(option)
    return selected_options


def format_submission_lines(items: List[dict[str, Any]]) -> str:
    lines = []
    for item in items:
        lines.append(
            f"{item['label']}: {format_submitted_value(item['value'])}"
        )
    return "\n".join(lines)


def format_answer_lines(answers: List[dict[str, Any]]) -> str:
    lines = []
    for answer in answers:
        lines.append(
            f"{answer['question']}: "
            f"{format_submitted_value(answer['answer'])}"
        )
    return "\n".join(lines)


def homework_submission_summary_text(
    submitted_fields_text: str,
    submitted_answers_text: str,
) -> str:
    summary_sections = []
    if submitted_fields_text:
        summary_sections.append(submitted_fields_text)
    if submitted_answers_text:
        summary_sections.append(submitted_answers_text)
    return "\n\n".join(summary_sections)


def homework_confirmation_metadata(
    data: HomeworkConfirmationData,
) -> dict[str, Any]:
    return {
        "course_slug": data.course.slug,
        "course_title": data.course.title,
        "homework_slug": data.homework.slug,
        "homework_title": data.homework.title,
        "homework_due_at": data.homework.due_date.isoformat(),
        "submission_id": data.submission.id,
        "submitted_at": data.submission.submitted_at.isoformat(),
        "update_url": data.update_url,
        "profile_url": data.profile_url,
        "update_link_text": "Update your submission",
    }


def homework_confirmation_notification_context(
    profile_url: str,
) -> dict[str, str]:
    return {
        "notification_category": "homework and project submissions",
        "notification_footer": (
            "You are receiving this because homework and project "
            "submission emails are enabled in your profile."
        ),
        "notification_footer_text": (
            "If you don't want to receive these emails, you can turn "
            "off homework and project submission emails in your "
            f"profile: {profile_url}"
        ),
    }


def homework_confirmation_message_context(
    data: HomeworkConfirmationData,
) -> dict[str, str]:
    return {
        "email_subject": (
            f"Homework submission saved: {data.homework.title}"
        ),
        "email_preview": (
            "Your homework submission was saved. "
            "Review what you submitted and update it while the "
            "homework is open."
        ),
        "intro_text": (
            f"Your homework submission for {data.homework.title} in "
            f"{data.course.title} was saved."
        ),
        "update_text": (
            "You can update your submission while the homework "
            f"is open: {data.update_url}"
        ),
    }


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
    summary_text = homework_submission_summary_text(
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


def homework_confirmation_context(
    data: HomeworkConfirmationData,
) -> dict[str, Any]:
    submitted_content = homework_submitted_content(
        data.course,
        data.homework,
        data.submission,
    )

    return {
        **homework_confirmation_metadata(data),
        **homework_confirmation_notification_context(data.profile_url),
        **homework_confirmation_message_context(data),
        **submitted_content.context(),
    }


def build_homework_update_url(
    request: HttpRequest,
    course: Course,
    homework: Homework,
) -> str:
    path = reverse(
        "homework",
        kwargs={
            "course_slug": course.slug,
            "homework_slug": homework.slug,
        },
    )
    return absolute_url_with_fallback(request, path, label="homework")


def determine_answer_class(is_selected: bool, is_correct: bool) -> str:
    if is_correct:
        return "option-answer-correct"
    if is_selected:
        return "option-answer-incorrect"
    return "option-answer-none"


def process_question_options(
    homework: Homework, question: Question, answer: Answer
):
    if question.question_type in FREE_FORM_QUESTION_TYPES:
        return process_question_free_form(homework, question, answer)

    return process_question_options_multiple_choice_or_checkboxes(
        homework, question, answer
    )


def tryparsefloat(value: str) -> Optional[float]:
    try:
        return float(value)
    except ValueError:
        return None


def parse_time_spent_hours(
    value: Optional[str], field_label: str
) -> Optional[float]:
    """Parse a user-entered "hours spent" value.

    Returns None when nothing was provided (field left untouched).
    Accepts comma decimal separators ("2,5"), which mobile and many
    locale keyboards submit. Raises ValidationError on non-numeric input
    instead of letting float() raise an uncaught ValueError (a 500).
    """
    if value is None:
        return None

    value = value.strip()
    if not value:
        return None

    parsed = tryparsefloat(value.replace(",", "."))
    if parsed is None:
        raise ValidationError(
            f"Please enter a valid number of hours for {field_label} "
            "(for example, 2 or 2.5)."
        )
    return parsed


def _invalid_learning_in_public_link_error():
    return ValidationError(
        "Learning in public links must be valid HTTP or HTTPS URLs."
    )


def _validate_learning_in_public_link(url_validator, link):
    try:
        url_validator(link)
    except ValidationError:
        raise _invalid_learning_in_public_link_error()


def _is_blank_or_duplicate_link(link, cleaned_links):
    return len(link) == 0 or link in cleaned_links


def clean_learning_in_public_links(
    links: List[str], cap: int
) -> List[str]:
    url_validator = URLValidator(schemes=["http", "https"])
    cleaned_links = []

    for link in links:
        link = link.strip()
        if _is_blank_or_duplicate_link(link, cleaned_links):
            continue
        if len(cleaned_links) >= cap:
            break

        _validate_learning_in_public_link(url_validator, link)
        cleaned_links.append(link)

    return cleaned_links


def find_duplicate_learning_in_public_links(
    user: User,
    course: Course,
    links: List[str],
    current_submission: Optional[Submission],
) -> List[str]:
    if not links:
        return []

    candidate_links = set(links)
    duplicate_links = _duplicate_homework_learning_links(
        user=user,
        course=course,
        candidate_links=candidate_links,
        current_submission=current_submission,
    )
    duplicate_links.update(
        _duplicate_project_learning_links(
            user=user,
            course=course,
            candidate_links=candidate_links,
        )
    )

    return sorted(duplicate_links)


def _duplicate_homework_learning_links(
    *, user, course, candidate_links, current_submission
):
    submissions = _homework_submissions_with_learning_links(user, course)
    submissions = _exclude_current_submission(submissions, current_submission)
    return _duplicate_learning_links_from_submissions(
        submissions,
        candidate_links,
    )


def _homework_submissions_with_learning_links(user, course):
    return Submission.objects.filter(
        student=user,
        homework__course=course,
        learning_in_public_links__isnull=False,
    )


def _exclude_current_submission(submissions, current_submission):
    if current_submission and current_submission.pk:
        return submissions.exclude(pk=current_submission.pk)
    return submissions


def _duplicate_project_learning_links(*, user, course, candidate_links):
    submissions = ProjectSubmission.objects.filter(
        student=user,
        project__course=course,
        volunteer_review_only=False,
        learning_in_public_links__isnull=False,
    )
    return _duplicate_learning_links_from_submissions(
        submissions,
        candidate_links,
    )


def _duplicate_learning_links_from_submissions(submissions, candidate_links):
    duplicate_links = set()
    for submission in submissions:
        duplicate_links.update(
            _matching_learning_links(submission, candidate_links)
        )
    return duplicate_links


def _matching_learning_links(submission, candidate_links):
    matching_links = set()
    learning_links = submission.learning_in_public_links or []
    for link in learning_links:
        if link in candidate_links:
            matching_links.add(link)
    return matching_links


def send_homework_confirmation_email(
    user: User,
    course: Course,
    homework: Homework,
    submission: Submission,
    update_url: str,
) -> None:
    if not user.email:
        return

    send_transactional_email(
        homework_confirmation_payload(
            user=user,
            course=course,
            homework=homework,
            submission=submission,
            update_url=update_url,
        )
    )


def homework_confirmation_payload(
    *,
    user: User,
    course: Course,
    homework: Homework,
    submission: Submission,
    update_url: str,
) -> dict:
    return {
        "email": user.email,
        "template_key": email_templates.HOMEWORK_SUBMISSION_CONFIRMATION,
        "category_tag": "submission-results",
        "idempotency_key": homework_confirmation_idempotency_key(
            submission
        ),
        "context": homework_confirmation_payload_context(
            course,
            homework,
            submission,
            update_url,
        ),
        "metadata": homework_confirmation_email_metadata(
            course, homework, submission
        ),
    }


def homework_confirmation_payload_context(
    course: Course,
    homework: Homework,
    submission: Submission,
    update_url: str,
) -> dict[str, Any]:
    profile_url = build_account_settings_url(request_base_url(update_url))
    data = HomeworkConfirmationData(
        course=course,
        homework=homework,
        submission=submission,
        update_url=update_url,
        profile_url=profile_url,
    )
    return homework_confirmation_context(data)


def homework_confirmation_idempotency_key(submission: Submission) -> str:
    return (
        f"homework-submission:{submission.id}:"
        f"{submission.submitted_at.isoformat()}"
    )


def homework_confirmation_email_metadata(
    course: Course,
    homework: Homework,
    submission: Submission,
) -> dict:
    return {
        "source": "course-management-platform",
        "event": "homework_submission",
        "course_slug": course.slug,
        "homework_slug": homework.slug,
        "submission_id": submission.id,
    }


def request_base_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def build_account_settings_url(base_url: str) -> str:
    path = reverse("account_settings")
    if base_url:
        return urljoin(f"{base_url}/", path.lstrip("/"))
    return path


def _apply_homework_submission_fields(field_data):
    """Populate the optional submission fields enabled for this homework."""
    _apply_homework_url_field(field_data)
    _apply_learning_in_public_links(field_data)
    _apply_time_spent_fields(field_data)
    _apply_problems_comments_field(field_data)
    _apply_faq_contribution_field(field_data)


def _apply_homework_url_field(field_data):
    if field_data.homework.homework_url_field:
        field_data.submission.homework_link = (
            field_data.request.POST.get("homework_url")
        )


def _apply_learning_in_public_links(field_data):
    if field_data.homework.learning_in_public_cap > 0:
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


def _apply_time_spent_fields(field_data):
    _apply_time_spent_field(
        field_data.submission,
        field_data.request,
        enabled=field_data.homework.time_spent_lectures_field,
        post_key="time_spent_lectures",
        model_field="time_spent_lectures",
        field_label="time spent on lectures",
    )
    _apply_time_spent_field(
        field_data.submission,
        field_data.request,
        enabled=field_data.homework.time_spent_homework_field,
        post_key="time_spent_homework",
        model_field="time_spent_homework",
        field_label="time spent on homework",
    )


def _apply_time_spent_field(
    submission, request, *, enabled, post_key, model_field, field_label
):
    if not enabled:
        return

    time_spent = parse_time_spent_hours(
        request.POST.get(post_key),
        field_label,
    )
    if time_spent is not None:
        setattr(submission, model_field, time_spent)


def _apply_problems_comments_field(field_data):
    if field_data.course.homework_problems_comments_field:
        field_data.submission.problems_comments = (
            field_data.request.POST.get(
                "problems_comments",
                "",
            ).strip()
        )


def _apply_faq_contribution_field(field_data):
    if field_data.homework.faq_contribution_field:
        field_data.submission.faq_contribution_url = (
            clean_faq_contribution_url(
                field_data.request.POST.get("faq_contribution_url", "")
            ).strip()
        )


def _homework_answers_from_post(request):
    answers_dict = {}
    posted_answers = request.POST.lists()
    for answer_id, answer in posted_answers:
        if not answer_id.startswith("answer_"):
            continue
        cleaned_answer_items = []
        for answer_item in answer:
            cleaned_answer_item = answer_item.strip()
            cleaned_answer_items.append(cleaned_answer_item)
        answers_dict[answer_id] = ",".join(cleaned_answer_items)
    return answers_dict


def _homework_submission_for_user(user, course, homework, submission):
    if submission:
        submission.submitted_at = timezone.now()
        return submission

    enrollment, _ = Enrollment.objects.get_or_create(
        student=user,
        course=course,
    )
    return Submission.objects.create(
        homework=homework,
        student=user,
        enrollment=enrollment,
    )


def _save_homework_answers(submission, questions, answers_dict):
    for question in questions:
        answer_text = answers_dict.get(f"answer_{question.id}")
        Answer.objects.update_or_create(
            submission=submission,
            question=question,
            defaults={"answer_text": answer_text},
        )


def _register_homework_submission_callbacks(data, submission):
    user = data.request.user
    update_url = build_homework_update_url(
        data.request,
        data.course,
        data.homework,
    )
    transaction.on_commit(
        lambda: send_homework_confirmation_email(
            user=user,
            course=data.course,
            homework=data.homework,
            submission=submission,
            update_url=update_url,
        )
    )
    transaction.on_commit(
        lambda: sync_homework_submission_to_datamailer(submission)
    )


def _homework_submission_success_response(request, course, homework):
    success_message = (
        "Thank you for submitting your homework, now your solution "
        + "is saved. You can update it at any point. You will see "
        + "your score after the form is closed."
    )
    messages.success(
        request,
        success_message,
        extra_tags="homework",
    )
    return redirect(
        "homework",
        course_slug=course.slug,
        homework_slug=homework.slug,
    )


def _save_homework_submission_data(data):
    user = data.request.user
    answers_dict = _homework_answers_from_post(data.request)
    submission = _homework_submission_for_user(
        user,
        data.course,
        data.homework,
        data.submission,
    )
    _save_homework_answers(submission, data.questions, answers_dict)
    field_data = HomeworkSubmissionFieldData(
        submission=submission,
        request=data.request,
        course=data.course,
        homework=data.homework,
        user=user,
    )
    _apply_homework_submission_fields(field_data)
    submission.full_clean()
    submission.save()
    return submission


def process_homework_submission(data: HomeworkPostData):
    submission = _save_homework_submission_data(data)
    _register_homework_submission_callbacks(data, submission)
    return _homework_submission_success_response(
        data.request,
        data.course,
        data.homework,
    )


def homework_detail_build_context_not_authenticated(
    course: Course,
    homework: Homework,
    questions: List[Question],
) -> dict:
    context = {
        "course": course,
        "homework": homework,
        "question_answers": question_answers_for_submission(
            homework,
            questions,
            None,
        ),
        "is_authenticated": False,
        "disabled": True,
        "accepting_submissions": (
            homework.state == HomeworkState.OPEN.value
        ),
    }

    return context


def submission_answer_map(
    submission: Optional[Submission],
) -> dict[int, Answer]:
    if not submission:
        return {}

    answers = Answer.objects.filter(
        submission=submission
    ).select_related("question")
    answer_map = {}
    for answer in answers:
        answer_map[answer.question.id] = answer
    return answer_map


def question_answers_for_submission(
    homework: Homework,
    questions: List[Question],
    submission: Optional[Submission],
) -> list[tuple[Question, dict]]:
    question_answers_map = submission_answer_map(submission)
    question_answers = []

    for question in questions:
        answer = question_answers_map.get(question.id)
        processed_answer = process_question_options(
            homework,
            question,
            answer,
        )
        question_answers.append((question, processed_answer))

    return question_answers


def learning_in_public_disabled(
    enrollment: Optional["Enrollment"],
) -> bool:
    return (
        enrollment.disable_learning_in_public if enrollment else False
    )


def homework_detail_build_context_authenticated(
    course: Course,
    homework: Homework,
    questions: List[Question],
    submission: Optional[Submission],
    enrollment: Optional["Enrollment"] = None,
) -> dict:
    context = {
        "course": course,
        "homework": homework,
        "question_answers": question_answers_for_submission(
            homework,
            questions,
            submission,
        ),
        "submission": submission,
        "is_authenticated": True,
        "disable_learning_in_public": learning_in_public_disabled(
            enrollment
        ),
    }
    context.update(homework_state_context(homework))
    return context


def answer_from_post(
    request: HttpRequest, question: Question
) -> Answer:
    answer_text = ",".join(
        value.strip()
        for value in request.POST.getlist(f"answer_{question.id}")
    )
    return Answer(question=question, answer_text=answer_text)


def homework_state_context(homework: Homework) -> dict[str, bool]:
    accepting_submissions = homework.state == HomeworkState.OPEN.value
    return {
        "disabled": not accepting_submissions,
        "accepting_submissions": accepting_submissions,
    }


def bound_homework_submission_from_post(
    data: HomeworkPostData,
) -> Submission:
    bound_submission = data.submission or Submission(
        homework=data.homework,
        student=data.request.user,
        enrollment=data.enrollment,
    )
    apply_homework_post_preview_fields(
        data.request,
        data.course,
        data.homework,
        bound_submission,
    )
    return bound_submission


def _post_preview_value(request: HttpRequest, key: str) -> str:
    return request.POST.get(key, "")


def _post_preview_learning_links(request: HttpRequest) -> list[str]:
    links = []
    raw_links = request.POST.getlist("learning_in_public_links[]")
    for raw_link in raw_links:
        link = raw_link.strip()
        if link:
            links.append(link)
    return links


def _apply_post_preview_homework_url(
    request: HttpRequest,
    homework: Homework,
    submission: Submission,
) -> None:
    if homework.homework_url_field:
        submission.homework_link = _post_preview_value(
            request,
            "homework_url",
        )


def _apply_post_preview_learning_links(
    request: HttpRequest,
    homework: Homework,
    submission: Submission,
) -> None:
    if homework.learning_in_public_cap > 0:
        submission.learning_in_public_links = (
            _post_preview_learning_links(request)
        )


def _apply_post_preview_time_spent(
    request: HttpRequest,
    homework: Homework,
    submission: Submission,
) -> None:
    if homework.time_spent_lectures_field:
        submission.time_spent_lectures = _post_preview_value(
            request,
            "time_spent_lectures",
        )

    if homework.time_spent_homework_field:
        submission.time_spent_homework = _post_preview_value(
            request,
            "time_spent_homework",
        )


def _apply_post_preview_comments(
    request: HttpRequest,
    course: Course,
    submission: Submission,
) -> None:
    if course.homework_problems_comments_field:
        submission.problems_comments = _post_preview_value(
            request,
            "problems_comments",
        )


def _apply_post_preview_faq_contribution(
    request: HttpRequest,
    homework: Homework,
    submission: Submission,
) -> None:
    if homework.faq_contribution_field:
        submission.faq_contribution_url = _post_preview_value(
            request,
            "faq_contribution_url",
        )


def apply_homework_post_preview_fields(
    request: HttpRequest,
    course: Course,
    homework: Homework,
    submission: Submission,
) -> None:
    _apply_post_preview_homework_url(request, homework, submission)
    _apply_post_preview_learning_links(request, homework, submission)
    _apply_post_preview_time_spent(request, homework, submission)
    _apply_post_preview_comments(request, course, submission)
    _apply_post_preview_faq_contribution(request, homework, submission)


def question_answers_from_post(
    request: HttpRequest,
    homework: Homework,
    questions: List[Question],
) -> list[tuple[Question, dict]]:
    question_answers = []
    for question in questions:
        answer = answer_from_post(request, question)
        processed_answer = process_question_options(
            homework,
            question,
            answer,
        )
        question_answers.append((question, processed_answer))
    return question_answers


def homework_detail_build_context_from_post(
    data: HomeworkPostData,
) -> dict:
    bound_submission = bound_homework_submission_from_post(data)
    context = {
        "course": data.course,
        "homework": data.homework,
        "question_answers": question_answers_from_post(
            data.request,
            data.homework,
            data.questions,
        ),
        "submission": bound_submission,
        "is_authenticated": True,
        "disable_learning_in_public": (
            data.enrollment.disable_learning_in_public
        ),
    }
    context.update(homework_state_context(data.homework))
    return context


def homework_error_fields(error: ValidationError) -> set[str]:
    field_map = {
        "homework_link": "homework_url",
        "learning_in_public_links": "learning_in_public_links",
        "time_spent_lectures": "time_spent_lectures",
        "time_spent_homework": "time_spent_homework",
        "problems_comments": "problems_comments",
        "faq_contribution_url": "faq_contribution_url",
    }

    if not hasattr(error, "message_dict"):
        return set()

    fields = set()
    error_field_names = error.message_dict
    for field_name in error_field_names:
        if field_name in field_map:
            field = field_map[field_name]
            fields.add(field)
    return fields


def redirect_to_homework(course: Course, homework: Homework):
    return redirect(
        "homework",
        course_slug=course.slug,
        homework_slug=homework.slug,
    )


def closed_homework_submission_response(
    request: HttpRequest,
    course: Course,
    homework: Homework,
):
    messages.error(
        request,
        "This homework is not open for submissions.",
        extra_tags="homework",
    )
    return redirect_to_homework(course, homework)


def homework_validation_context(
    data: HomeworkPostData,
    error: ValidationError,
) -> dict:
    context = homework_detail_build_context_from_post(data)
    context["errors"] = error.messages
    context["error_fields"] = homework_error_fields(error)
    return context


def submit_homework_post(
    data: HomeworkPostData,
):
    with transaction.atomic():
        return process_homework_submission(data)


def handle_homework_post(data: HomeworkPostData):
    if data.homework.state != HomeworkState.OPEN.value:
        return closed_homework_submission_response(
            data.request,
            data.course,
            data.homework,
        )

    try:
        return submit_homework_post(data)
    except ValidationError as error:
        return homework_validation_context(
            data=data,
            error=error,
        )


def homework_detail_objects(course_slug: str, homework_slug: str):
    course = get_object_or_404(Course, slug=course_slug)
    homework = get_object_or_404(
        Homework,
        course=course,
        slug=homework_slug,
    )
    questions = Question.objects.filter(homework=homework).order_by(
        "id"
    )
    return course, homework, questions


def authenticated_homework_context(
    user: User,
    course: Course,
    homework: Homework,
    questions: List[Question],
):
    submission = Submission.objects.filter(
        homework=homework,
        student=user,
    ).first()
    enrollment, _ = Enrollment.objects.get_or_create(
        student=user,
        course=course,
    )
    context = homework_detail_build_context_authenticated(
        course=course,
        homework=homework,
        questions=questions,
        submission=submission,
        enrollment=enrollment,
    )
    return context, submission, enrollment


def authenticated_homework_response(
    request: HttpRequest,
    course: Course,
    homework: Homework,
    questions: List[Question],
):
    context, submission, enrollment = authenticated_homework_context(
        user=request.user,
        course=course,
        homework=homework,
        questions=questions,
    )

    if request.method != "POST":
        return render(request, "homework/homework.html", context)

    post_data = HomeworkPostData(
        request=request,
        course=course,
        homework=homework,
        questions=questions,
        submission=submission,
        enrollment=enrollment,
    )
    post_result = handle_homework_post(post_data)
    if not isinstance(post_result, dict):
        return post_result

    return render(request, "homework/homework.html", post_result)


def homework_view(
    request: HttpRequest, course_slug: str, homework_slug: str
):
    course, homework, questions = homework_detail_objects(
        course_slug,
        homework_slug,
    )
    user = request.user

    if not user.is_authenticated:
        context = homework_detail_build_context_not_authenticated(
            course=course, homework=homework, questions=questions
        )
        return render(request, "homework/homework.html", context)

    return authenticated_homework_response(
        request,
        course,
        homework,
        questions,
    )


def homework_statistics(request, course_slug, homework_slug):
    course = get_object_or_404(Course, slug=course_slug)
    homework = get_object_or_404(
        Homework, course=course, slug=homework_slug
    )

    if not homework.is_scored():
        messages.error(
            request,
            "This homework is not scored yet, so there are no available statistics.",
            extra_tags="homework",
        )
        return redirect(
            "homework",
            course_slug=course.slug,
            homework_slug=homework.slug,
        )

    stats = calculate_homework_statistics(homework, force=False)

    context = {
        "course": course,
        "homework": homework,
        "stats": stats,
    }

    return render(request, "homework/stats.html", context)


def homework_submissions(request, course_slug, homework_slug):
    # Check if user is staff - if not, redirect to homework view with error
    if not request.user.is_authenticated or not request.user.is_staff:
        messages.error(
            request,
            "You do not have permission to view this page.",
            extra_tags="homework",
        )
        return redirect(
            "homework",
            course_slug=course_slug,
            homework_slug=homework_slug,
        )

    # Staff users: redirect to cadmin view
    return redirect(
        "cadmin_homework_submissions",
        course_slug=course_slug,
        homework_slug=homework_slug,
    )
