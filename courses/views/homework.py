import logging

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


def process_quesion_free_form(
    homework: Homework, question: Question, answer: Answer
):
    if not homework.is_scored():
        if not answer:
            return {"text": ""}
        else:
            return {"text": answer.answer_text}

    # homework is scored - show correct answers
    if (
        not answer
        or not answer.answer_text
        or not answer.answer_text.strip()
    ):
        return {
            "text": question.correct_answer,
            "no_answer_submitted": True,
        }

    # the homework is scored and we want to show the answers

    is_correct = is_free_form_answer_correct(question, answer)

    if is_correct:
        correctly_selected = "option-answer-correct"
    else:
        correctly_selected = "option-answer-incorrect"

    return {
        "text": answer.answer_text,
        "correctly_selected_class": correctly_selected,
    }


def process_question_options_multiple_choice_or_checkboxes(
    homework: Homework, question: Question, answer: Optional[Answer]
):
    options = []

    if answer:
        selected_options = extract_selected_options(answer)
    else:
        # no answer yet, so we need to show just options
        selected_options = []

    possible_answers = question.get_possible_answers()

    if homework.is_scored():
        correct_indices = question.get_correct_answer_indices()

    for zero_based_index, option in enumerate(possible_answers):
        index = zero_based_index + 1
        is_selected = index in selected_options

        processed_answer = {
            "value": option,
            "is_selected": is_selected,
            "index": index,
        }

        if homework.state == HomeworkState.SCORED.value:
            is_correct = index in correct_indices

            correctly_selected = determine_answer_class(
                is_selected, is_correct
            )

            processed_answer["is_correct"] = is_correct
            processed_answer["correctly_selected_class"] = (
                correctly_selected
            )

        options.append(processed_answer)

    result = {"options": options}

    # Check if no answer was submitted for a scored homework
    if homework.is_scored() and len(selected_options) == 0:
        result["no_answer_submitted"] = True

    return result


def extract_selected_options(answer):
    if not answer:
        return []

    return extract_selected_option_indexes(answer.answer_text)


def extract_selected_option_indexes(
    answer_text: Optional[str],
) -> List[int]:
    answer_text = answer_text or ""
    answer_text = answer_text.strip()

    if not answer_text:
        return []

    selected_options = answer_text.strip().split(",")

    result = []

    for option in selected_options:
        option = option.strip()
        if not option:
            continue
        try:
            result.append(int(option))
        except ValueError:
            pass

    return result


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
        if 1 <= index <= len(possible_answers):
            selected_options.append(
                f"{index}. {possible_answers[index - 1]}"
            )
        else:
            selected_options.append(str(index))

    return ", ".join(selected_options)


def homework_submission_fields(
    course: Course,
    homework: Homework,
    submission: Submission,
) -> List[dict[str, Any]]:
    fields = []

    if homework.homework_url_field:
        fields.append(
            {
                "key": "homework_url",
                "label": "Homework URL",
                "value": submission.homework_link or "",
            }
        )

    if homework.learning_in_public_cap > 0:
        links = submission.learning_in_public_links or []
        fields.append(
            {
                "key": "learning_in_public_links",
                "label": "Learning in public links",
                "value": "\n".join(links),
                "values": links,
            }
        )

    if homework.time_spent_lectures_field:
        fields.append(
            {
                "key": "time_spent_lectures",
                "label": "Time spent on lectures",
                "value": format_hours(submission.time_spent_lectures),
            }
        )

    if homework.time_spent_homework_field:
        fields.append(
            {
                "key": "time_spent_homework",
                "label": "Time spent on homework",
                "value": format_hours(submission.time_spent_homework),
            }
        )

    if course.homework_problems_comments_field:
        fields.append(
            {
                "key": "problems_comments",
                "label": "Problems, comments, or feedback",
                "value": submission.problems_comments or "",
            }
        )

    if homework.faq_contribution_field:
        fields.append(
            {
                "key": "faq_contribution_url",
                "label": "FAQ contribution URL",
                "value": submission.faq_contribution_url or "",
            }
        )

    return fields


def homework_submitted_answers(
    submission: Submission,
) -> List[dict[str, Any]]:
    answers = (
        Answer.objects.filter(submission=submission)
        .select_related("question")
        .order_by("question_id")
    )

    result = []
    for answer in answers:
        question = answer.question
        raw_answer = answer.answer_text or ""
        display_answer = raw_answer
        selected_options = []

        if question.question_type in CHOICE_QUESTION_TYPES:
            possible_answers = question.get_possible_answers()
            selected_indexes = extract_selected_option_indexes(
                raw_answer
            )
            for index in selected_indexes:
                value = ""
                if 1 <= index <= len(possible_answers):
                    value = possible_answers[index - 1]
                selected_options.append(
                    {"index": index, "value": value}
                )
            display_answer = format_selected_answer(
                question,
                raw_answer,
            )

        result.append(
            {
                "question_id": question.id,
                "question": question.text,
                "question_type": question.question_type,
                "answer": display_answer,
                "raw_answer": raw_answer,
                "selected_options": selected_options,
            }
        )

    return result


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


def homework_confirmation_context(
    course: Course,
    homework: Homework,
    submission: Submission,
    update_url: str,
    profile_url: str,
) -> dict[str, Any]:
    submission_fields = homework_submission_fields(
        course,
        homework,
        submission,
    )
    submitted_answers = homework_submitted_answers(submission)
    submitted_fields_text = format_submission_lines(submission_fields)
    submitted_answers_text = format_answer_lines(submitted_answers)

    summary_sections = []
    if submitted_fields_text:
        summary_sections.append(submitted_fields_text)
    if submitted_answers_text:
        summary_sections.append(submitted_answers_text)

    return {
        "course_slug": course.slug,
        "course_title": course.title,
        "homework_slug": homework.slug,
        "homework_title": homework.title,
        "homework_due_at": homework.due_date.isoformat(),
        "submission_id": submission.id,
        "submitted_at": submission.submitted_at.isoformat(),
        "update_url": update_url,
        "profile_url": profile_url,
        "update_link_text": "Update your submission",
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
        "email_subject": f"Homework submission saved: {homework.title}",
        "email_preview": (
            "Your homework submission was saved. "
            "Review what you submitted and update it while the "
            "homework is open."
        ),
        "intro_text": (
            f"Your homework submission for {homework.title} in "
            f"{course.title} was saved."
        ),
        "update_text": (
            "You can update your submission while the homework "
            f"is open: {update_url}"
        ),
        "submission_fields": submission_fields,
        "submitted_answers": submitted_answers,
        "submitted_fields_text": submitted_fields_text,
        "submitted_answers_text": submitted_answers_text,
        "submission_summary_text": "\n\n".join(summary_sections),
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
    if is_selected and is_correct:
        return "option-answer-correct"
    if not is_selected and is_correct:
        return "option-answer-correct"
    if is_selected and not is_correct:
        return "option-answer-incorrect"
    return "option-answer-none"


def process_question_options(
    homework: Homework, question: Question, answer: Answer
):
    if question.question_type == QuestionTypes.FREE_FORM.value:
        return process_quesion_free_form(homework, question, answer)

    if question.question_type == QuestionTypes.FREE_FORM_LONG.value:
        return process_quesion_free_form(homework, question, answer)

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


def clean_learning_in_public_links(
    links: List[str], cap: int
) -> List[str]:
    url_validator = URLValidator(schemes=["http", "https"])
    cleaned_links = []

    for link in links:
        link = link.strip()
        if len(link) == 0:
            continue
        if link in cleaned_links:
            continue
        if len(cleaned_links) >= cap:
            break

        try:
            url_validator(link)
        except ValidationError:
            raise ValidationError(
                "Learning in public links must be valid HTTP or HTTPS URLs."
            )

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

    links_set = set(links)
    duplicate_links = set()

    homework_submissions = Submission.objects.filter(
        student=user,
        homework__course=course,
        learning_in_public_links__isnull=False,
    )
    if current_submission and current_submission.pk:
        homework_submissions = homework_submissions.exclude(
            pk=current_submission.pk
        )

    for submitted_homework in homework_submissions:
        duplicate_links.update(
            link
            for link in (
                submitted_homework.learning_in_public_links or []
            )
            if link in links_set
        )

    project_submissions = ProjectSubmission.objects.filter(
        student=user,
        project__course=course,
        volunteer_review_only=False,
        learning_in_public_links__isnull=False,
    )
    for submitted_project in project_submissions:
        duplicate_links.update(
            link
            for link in (
                submitted_project.learning_in_public_links or []
            )
            if link in links_set
        )

    return sorted(duplicate_links)


def send_homework_confirmation_email(
    user: User,
    course: Course,
    homework: Homework,
    submission: Submission,
    update_url: str,
) -> None:
    if not user.email:
        return
    if not getattr(user, "email_submission_confirmations", True):
        return

    context = homework_confirmation_context(
        course=course,
        homework=homework,
        submission=submission,
        update_url=update_url,
        profile_url=build_account_settings_url(
            request_base_url(update_url)
        ),
    )

    send_transactional_email(
        {
            "email": user.email,
            "template_key": (
                email_templates.HOMEWORK_SUBMISSION_CONFIRMATION
            ),
            "idempotency_key": (
                f"homework-submission:{submission.id}:"
                f"{submission.submitted_at.isoformat()}"
            ),
            "context": context,
            "metadata": {
                "source": "course-management-platform",
                "event": "homework_submission",
                "course_slug": course.slug,
                "homework_slug": homework.slug,
                "submission_id": submission.id,
            },
        }
    )


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


def _apply_homework_submission_fields(
    submission, request, course, homework, user
):
    """Populate the optional submission fields enabled for this homework."""
    if homework.homework_url_field:
        submission.homework_link = request.POST.get("homework_url")

    if homework.learning_in_public_cap > 0:
        links = request.POST.getlist("learning_in_public_links[]")
        cleaned_links = clean_learning_in_public_links(
            links, homework.learning_in_public_cap
        )
        duplicate_links = find_duplicate_learning_in_public_links(
            user=user,
            course=course,
            links=cleaned_links,
            current_submission=submission,
        )
        if duplicate_links:
            raise ValidationError(
                "Learning in public links were already used in another "
                f"submission: {', '.join(duplicate_links)}"
            )
        submission.learning_in_public_links = cleaned_links

    if homework.time_spent_lectures_field:
        time_spent_lectures = parse_time_spent_hours(
            request.POST.get("time_spent_lectures"),
            "time spent on lectures",
        )
        if time_spent_lectures is not None:
            submission.time_spent_lectures = time_spent_lectures

    if homework.time_spent_homework_field:
        time_spent_homework = parse_time_spent_hours(
            request.POST.get("time_spent_homework"),
            "time spent on homework",
        )
        if time_spent_homework is not None:
            submission.time_spent_homework = time_spent_homework

    if course.homework_problems_comments_field:
        submission.problems_comments = request.POST.get(
            "problems_comments", ""
        ).strip()

    if homework.faq_contribution_field:
        submission.faq_contribution_url = clean_faq_contribution_url(
            request.POST.get("faq_contribution_url", "")
        ).strip()


def process_homework_submission(
    request: HttpRequest,
    course: Course,
    homework: Homework,
    questions: List[Question],
    submission: Optional[Submission],
):
    user = request.user

    answers_dict = {}
    for answer_id, answer in request.POST.lists():
        if not answer_id.startswith("answer_"):
            continue
        answer = [a.strip() for a in answer]
        answers_dict[answer_id] = ",".join(answer)

    if submission:
        submission.submitted_at = timezone.now()
    else:
        enrollment, _ = Enrollment.objects.get_or_create(
            student=user,
            course=course,
        )
        submission = Submission.objects.create(
            homework=homework,
            student=user,
            enrollment=enrollment,
        )

    for question in questions:
        answer_text = answers_dict.get(f"answer_{question.id}")

        values = {"answer_text": answer_text}

        Answer.objects.update_or_create(
            submission=submission,
            question=question,
            defaults=values,
        )

    _apply_homework_submission_fields(
        submission, request, course, homework, user
    )

    submission.full_clean()
    submission.save()
    update_url = build_homework_update_url(request, course, homework)
    transaction.on_commit(
        lambda: send_homework_confirmation_email(
            user=user,
            course=course,
            homework=homework,
            submission=submission,
            update_url=update_url,
        )
    )
    transaction.on_commit(
        lambda: sync_homework_submission_to_datamailer(submission)
    )

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


def homework_detail_build_context_not_authenticated(
    course: Course,
    homework: Homework,
    questions: List[Question],
) -> dict:
    question_answers = []
    for question in questions:
        options = process_question_options(homework, question, None)
        question_answers.append((question, options))

    context = {
        "course": course,
        "homework": homework,
        "question_answers": question_answers,
        "is_authenticated": False,
        "disabled": True,
        "accepting_submissions": (
            homework.state == HomeworkState.OPEN.value
        ),
    }

    return context


def homework_detail_build_context_authenticated(
    course: Course,
    homework: Homework,
    questions: List[Question],
    submission: Optional[Submission],
    enrollment: Optional["Enrollment"] = None,
) -> dict:
    if submission:
        answers = Answer.objects.filter(
            submission=submission
        ).select_related("question")

        question_answers_map = {
            answer.question.id: answer for answer in answers
        }
    else:
        question_answers_map = {}

    # Pairing questions with their answers
    question_answers = []

    for question in questions:
        answer = question_answers_map.get(question.id)
        processed_answer = process_question_options(
            homework, question, answer
        )

        pair = (question, processed_answer)
        question_answers.append(pair)

    disabled = homework.state != HomeworkState.OPEN.value
    accepting_submissions = homework.state == HomeworkState.OPEN.value

    # Check if learning in public is disabled for this enrollment
    disable_learning_in_public = (
        enrollment.disable_learning_in_public if enrollment else False
    )

    context = {
        "course": course,
        "homework": homework,
        "question_answers": question_answers,
        "submission": submission,
        "is_authenticated": True,
        "disabled": disabled,
        "accepting_submissions": accepting_submissions,
        "disable_learning_in_public": disable_learning_in_public,
    }

    return context


def answer_from_post(
    request: HttpRequest, question: Question
) -> Answer:
    answer_text = ",".join(
        value.strip()
        for value in request.POST.getlist(f"answer_{question.id}")
    )
    return Answer(question=question, answer_text=answer_text)


def homework_detail_build_context_from_post(
    request: HttpRequest,
    course: Course,
    homework: Homework,
    questions: List[Question],
    submission: Optional[Submission],
    enrollment: Enrollment,
) -> dict:
    bound_submission = submission or Submission(
        homework=homework,
        student=request.user,
        enrollment=enrollment,
    )

    if homework.homework_url_field:
        bound_submission.homework_link = request.POST.get(
            "homework_url", ""
        )

    if homework.learning_in_public_cap > 0:
        bound_submission.learning_in_public_links = [
            link.strip()
            for link in request.POST.getlist(
                "learning_in_public_links[]"
            )
            if link.strip()
        ]

    if homework.time_spent_lectures_field:
        bound_submission.time_spent_lectures = request.POST.get(
            "time_spent_lectures",
            "",
        )

    if homework.time_spent_homework_field:
        bound_submission.time_spent_homework = request.POST.get(
            "time_spent_homework",
            "",
        )

    if course.homework_problems_comments_field:
        bound_submission.problems_comments = request.POST.get(
            "problems_comments",
            "",
        )

    if homework.faq_contribution_field:
        bound_submission.faq_contribution_url = request.POST.get(
            "faq_contribution_url",
            "",
        )

    question_answers = []
    for question in questions:
        answer = answer_from_post(request, question)
        processed_answer = process_question_options(
            homework,
            question,
            answer,
        )
        question_answers.append((question, processed_answer))

    disabled = homework.state != HomeworkState.OPEN.value
    accepting_submissions = homework.state == HomeworkState.OPEN.value

    return {
        "course": course,
        "homework": homework,
        "question_answers": question_answers,
        "submission": bound_submission,
        "is_authenticated": True,
        "disabled": disabled,
        "accepting_submissions": accepting_submissions,
        "disable_learning_in_public": enrollment.disable_learning_in_public,
    }


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

    return {
        field_map[field_name]
        for field_name in error.message_dict
        if field_name in field_map
    }


def homework_view(
    request: HttpRequest, course_slug: str, homework_slug: str
):
    course = get_object_or_404(Course, slug=course_slug)

    homework = get_object_or_404(
        Homework, course=course, slug=homework_slug
    )
    questions = Question.objects.filter(homework=homework).order_by(
        "id"
    )

    user = request.user

    if not user.is_authenticated:
        context = homework_detail_build_context_not_authenticated(
            course=course, homework=homework, questions=questions
        )
        return render(request, "homework/homework.html", context)

    submission = Submission.objects.filter(
        homework=homework, student=user
    ).first()

    # Get or create enrollment for the user
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

    # Process the form submission
    if request.method == "POST":
        if homework.state != HomeworkState.OPEN.value:
            messages.error(
                request,
                "This homework is not open for submissions.",
                extra_tags="homework",
            )
            return redirect(
                "homework",
                course_slug=course.slug,
                homework_slug=homework.slug,
            )

        try:
            with transaction.atomic():
                return process_homework_submission(
                    request=request,
                    course=course,
                    homework=homework,
                    questions=questions,
                    submission=submission,
                )
        except ValidationError as e:
            context = homework_detail_build_context_from_post(
                request=request,
                course=course,
                homework=homework,
                questions=questions,
                submission=submission,
                enrollment=enrollment,
            )
            context["errors"] = e.messages
            context["error_fields"] = homework_error_fields(e)

    return render(request, "homework/homework.html", context)


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
