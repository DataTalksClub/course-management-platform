from dataclasses import dataclass

from django.contrib import messages
from django.core.paginator import Page
from django.db.models import Q
from django.http import HttpRequest
from django.shortcuts import get_object_or_404, redirect, render

from course_management.datamailer.sync import send_homework_score_notification
from courses.models import Answer, Course, Homework, Question, Submission
from courses.scoring import (
    HomeworkScoringStatus,
    clear_correct_answers,
    fill_correct_answers,
    score_homework_submissions,
)
from cadmin.forms import HomeworkSubmissionEditForm
from cadmin.services import update_homework_submission_from_admin
from .helpers import (
    first_form_error,
    paginate_queryset,
    pagination_querystring,
    redirect_after_action,
    staff_required,
)


@dataclass(frozen=True)
class HomeworkSubmissionsContextData:
    request: HttpRequest
    course: Course
    homework: Homework
    submissions_page: Page
    search_query: str


@dataclass(frozen=True)
class HomeworkSubmissionEditPageData:
    request: HttpRequest
    course: Course
    homework: Homework
    submission: Submission
    questions: list
    questions_with_answers: list


@dataclass(frozen=True)
class HomeworkSubmissionEditObjects:
    course: Course
    homework: Homework
    submission: Submission


@dataclass(frozen=True)
class HomeworkSubmissionQuestions:
    questions: list
    questions_with_answers: list


@staff_required
def homework_score(request, course_slug, homework_slug):
    """Score a homework"""
    if request.method != "POST":
        return redirect("cadmin_course", course_slug=course_slug)
    course = get_object_or_404(Course, slug=course_slug)
    homework = get_object_or_404(
        Homework, course=course, slug=homework_slug
    )

    status, message = score_homework_submissions(homework.id)

    if status == HomeworkScoringStatus.OK:
        messages.success(request, message)
        send_homework_score_notification(homework)
    else:
        messages.warning(request, message)

    return redirect_after_action(
        request, "cadmin_course", course_slug=course_slug
    )


@staff_required
def homework_set_correct_answers(request, course_slug, homework_slug):
    """Set correct answers to most popular for a homework"""
    if request.method != "POST":
        return redirect("cadmin_course", course_slug=course_slug)
    course = get_object_or_404(Course, slug=course_slug)
    homework = get_object_or_404(
        Homework, course=course, slug=homework_slug
    )

    fill_correct_answers(homework)

    messages.success(
        request,
        f"Correct answers for {homework.title} set to most popular",
    )

    return redirect_after_action(
        request, "cadmin_course", course_slug=course_slug
    )


@staff_required
def homework_clear_correct_answers(request, course_slug, homework_slug):
    """Clear correct answers for a homework"""
    if request.method != "POST":
        return redirect("cadmin_course", course_slug=course_slug)
    course = get_object_or_404(Course, slug=course_slug)
    homework = get_object_or_404(
        Homework, course=course, slug=homework_slug
    )

    updated_count = clear_correct_answers(homework)

    messages.success(
        request,
        f"Correct answers for {updated_count} questions in {homework.title} cleared",
    )

    return redirect_after_action(
        request, "cadmin_course", course_slug=course_slug
    )


def _homework_submissions_queryset(homework, search_query):
    submissions = (
        Submission.objects.filter(homework=homework)
        .select_related("student", "enrollment")
        .order_by("-submitted_at")
    )

    if search_query:
        submissions = submissions.filter(
            Q(student__email__icontains=search_query)
            | Q(student__username__icontains=search_query)
        )
    return submissions


def _homework_submissions_data(submissions):
    submissions_data = []
    for submission in submissions:
        record = {"submission": submission}
        submissions_data.append(record)
    return submissions_data


def _homework_submissions_context(data):
    return {
        "course": data.course,
        "homework": data.homework,
        "submissions_data": _homework_submissions_data(
            data.submissions_page.object_list
        ),
        "submissions_page": data.submissions_page,
        "search_query": data.search_query,
        "pagination_querystring": pagination_querystring(data.request),
    }


@staff_required
def homework_submissions(request, course_slug, homework_slug):
    """View all submissions for a homework"""
    course = get_object_or_404(Course, slug=course_slug)
    homework = get_object_or_404(
        Homework, course=course, slug=homework_slug
    )
    search_query = request.GET.get("q", "").strip()
    submissions = _homework_submissions_queryset(homework, search_query)
    submissions_page = paginate_queryset(request, submissions)
    context_data = HomeworkSubmissionsContextData(
        request=request,
        course=course,
        homework=homework,
        submissions_page=submissions_page,
        search_query=search_query,
    )
    context = _homework_submissions_context(context_data)
    return render(request, "cadmin/homework_submissions.html", context)


def _questions_with_submission_answers(homework, submission):
    questions = Question.objects.filter(homework=homework).order_by(
        "id"
    )
    answers = Answer.objects.filter(
        submission=submission
    ).select_related("question")
    answer_map = {}
    for answer in answers:
        answer_map[answer.question_id] = answer

    questions_with_answers = []
    for question in questions:
        answer = answer_map.get(question.id)
        answer_text = ""
        if answer is not None:
            answer_text = answer.answer_text
        record = {
            "question": question,
            "answer": answer,
            "answer_text": answer_text,
        }
        questions_with_answers.append(record)
    return HomeworkSubmissionQuestions(
        questions=questions,
        questions_with_answers=questions_with_answers,
    )


def _homework_submission_edit_failed(data, message):
    messages.error(data.request, f"Error updating submission: {message}")
    return None


def _homework_submission_edit_success(data):
    messages.success(
        data.request,
        f"Homework submission for {data.submission.student.username} updated successfully",
    )
    return redirect(
        "cadmin_homework_submissions",
        course_slug=data.course.slug,
        homework_slug=data.homework.slug,
    )


def _handle_homework_submission_edit_post(data):
    form = HomeworkSubmissionEditForm(
        data.request.POST,
        submission=data.submission,
        questions=data.questions,
    )

    if not form.is_valid():
        return _homework_submission_edit_failed(
            data,
            first_form_error(form),
        )

    try:
        update_homework_submission_from_admin(
            data.submission,
            form.cleaned_data,
        )
    except Exception as e:
        return _homework_submission_edit_failed(data, e)

    return _homework_submission_edit_success(data)


def _homework_submission_edit_objects(
    course_slug, homework_slug, submission_id
):
    course = get_object_or_404(Course, slug=course_slug)
    homework = get_object_or_404(
        Homework, course=course, slug=homework_slug
    )
    submission = get_object_or_404(
        Submission, id=submission_id, homework=homework
    )
    return HomeworkSubmissionEditObjects(
        course=course,
        homework=homework,
        submission=submission,
    )


def _homework_submission_faq_data(request, submission):
    if request.method == "POST":
        return (
            request.POST.get("faq_contribution_url", "").strip(),
            request.POST.get("faq_score", submission.faq_score),
        )

    return submission.faq_contribution_url or "", submission.faq_score


def _homework_submission_edit_context(data):
    faq_contribution_url, faq_score = _homework_submission_faq_data(
        data.request,
        data.submission,
    )
    return {
        "course": data.course,
        "homework": data.homework,
        "submission": data.submission,
        "questions_with_answers": data.questions_with_answers,
        "learning_in_public_links_text": "\n".join(
            data.submission.learning_in_public_links or []
        ),
        "faq_contribution_url": faq_contribution_url,
        "faq_score": faq_score,
    }


def _homework_submission_edit_response(data):
    context = _homework_submission_edit_context(data)
    return render(
        data.request, "cadmin/homework_submission_edit.html", context
    )


@staff_required
def homework_submission_edit(
    request, course_slug, homework_slug, submission_id
):
    """Edit a homework submission"""
    edit_objects = _homework_submission_edit_objects(
        course_slug, homework_slug, submission_id
    )

    submission_questions = _questions_with_submission_answers(
        edit_objects.homework,
        edit_objects.submission,
    )
    edit_data = HomeworkSubmissionEditPageData(
        request=request,
        course=edit_objects.course,
        homework=edit_objects.homework,
        submission=edit_objects.submission,
        questions=submission_questions.questions,
        questions_with_answers=submission_questions.questions_with_answers,
    )

    if request.method == "POST":
        response = _handle_homework_submission_edit_post(edit_data)
        if response is not None:
            return response

    return _homework_submission_edit_response(edit_data)
