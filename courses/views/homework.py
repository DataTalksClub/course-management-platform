import logging

from typing import List, Optional

from django.http import HttpRequest

from django.contrib import messages
from django.utils import timezone
from django.shortcuts import render, get_object_or_404, redirect

from courses.models import (
    Course,
    Homework,
    Question,
    Answer,
    Submission,
    QuestionTypes,
    Enrollment,
    User,
)

from courses.scoring import is_free_form_answer_correct

logger = logging.getLogger(__name__)


NONE_LIST = [None]


def process_quesion_free_form(
    homework: Homework, question: Question, answer: Answer
):
    if not homework.is_scored:
        if not answer:
            return {"text": ""}
        else:
            return {"text": answer.answer_text}

    if not answer:
        return {"text": question.correct_answer}

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

    if homework.is_scored:
        correct_indices = question.get_correct_answer_indices()

    user_select_choice = True if len(selected_options) > 0 else False
    for zero_based_index, option in enumerate(possible_answers):
        index = zero_based_index + 1
        is_selected = index in selected_options

        processed_answer = {
            "value": option,
            "is_selected": is_selected,
            "index": index,
        }

        if homework.is_scored:
            is_correct = index in correct_indices

            correctly_selected = determine_answer_class(
                is_selected, is_correct, user_select_choice
            )

            processed_answer["correctly_selected_class"] = (
                correctly_selected
            )

        options.append(processed_answer)

    return {"options": options}


def extract_selected_options(answer):
    if not answer:
        return []

    answer_text = answer.answer_text or ""
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


def determine_answer_class(is_selected: bool, is_correct: bool, user_select_choice) -> str:
    if is_selected and is_correct:
        return "option-answer-correct"
    if not is_selected and not user_select_choice and is_correct:
        return "option-answer-correct"
    if is_selected and not is_correct:
        return "option-answer-incorrect"
    return "option-answer-none"


def process_question_options(
    homework: Homework, question: Question, answer: Answer
):
    if question.question_type == QuestionTypes.FREE_FORM.value:
        return process_quesion_free_form(homework, question, answer)

    return process_question_options_multiple_choice_or_checkboxes(
        homework, question, answer
    )


def tryparsefloat(value: str) -> Optional[float]:
    try:
        return float(value)
    except ValueError:
        return None


def clean_learning_in_public_links(
    links: List[str], cap: int
) -> List[str]:
    cleaned_links = []

    for link in links:
        if len(link) == 0:
            continue
        if link in cleaned_links:
            continue
        if len(cleaned_links) >= cap:
            break

        cleaned_links.append(link)

    return cleaned_links


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

    if homework.homework_url_field:
        submission.homework_link = request.POST.get("homework_url")

    if homework.learning_in_public_cap > 0:
        links = request.POST.getlist("learning_in_public_links[]")
        cleaned_links = clean_learning_in_public_links(
            links, homework.learning_in_public_cap
        )
        submission.learning_in_public_links = cleaned_links

    if homework.time_spent_lectures_field:
        time_spent_lectures = request.POST.get("time_spent_lectures")
        if (
            time_spent_lectures is not None
            and time_spent_lectures != ""
        ):
            submission.time_spent_lectures = float(time_spent_lectures)

    if homework.time_spent_homework_field:
        time_spent_homework = request.POST.get("time_spent_homework")
        if (
            time_spent_homework is not None
            and time_spent_homework != ""
        ):
            submission.time_spent_homework = float(time_spent_homework)

    if homework.problems_comments_field:
        problems_comments = request.POST.get("problems_comments", "")
        submission.problems_comments = problems_comments.strip()

    if homework.faq_contribution_field:
        faq_contribution = request.POST.get("faq_contribution", "")
        submission.faq_contribution = faq_contribution.strip()

    submission.save()

    messages.success(
        request,
        "Thank you for submitting your homework, now your solution is saved. You can update it at any point.",
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
    }

    return context


def homework_detail_build_context_authenticated(
    course: Course,
    homework: Homework,
    questions: List[Question],
    submission: Optional[Submission],
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

    disabled = homework.is_scored

    context = {
        "course": course,
        "homework": homework,
        "question_answers": question_answers,
        "submission": submission,
        "is_authenticated": True,
        "disabled": disabled,
        "accepting_submissions": not homework.is_scored,
    }

    return context


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

    logger.info(f"submission={submission}")

    # Process the form submission
    if request.method == "POST":
        return process_homework_submission(
            request=request,
            course=course,
            homework=homework,
            questions=questions,
            submission=submission,
        )

    context = homework_detail_build_context_authenticated(
        course=course,
        homework=homework,
        questions=questions,
        submission=submission,
    )

    return render(request, "homework/homework.html", context)


