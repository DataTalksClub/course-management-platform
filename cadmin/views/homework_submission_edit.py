from dataclasses import dataclass

from django.contrib import messages
from django.http import HttpRequest
from django.shortcuts import get_object_or_404, redirect, render

from courses.models.course import Course
from courses.models.homework import Answer, Homework, Question, Submission
from cadmin.forms import HomeworkSubmissionEditForm
from cadmin.services import update_homework_submission_from_admin
from cadmin.views.helpers import first_form_error


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


def homework_submission_edit_response(
    request, course_slug, homework_slug, submission_id
):
    edit_objects = homework_submission_edit_objects(
        course_slug, homework_slug, submission_id
    )

    questions, questions_with_answers = questions_with_submission_answers(
        edit_objects.homework,
        edit_objects.submission,
    )
    edit_data = HomeworkSubmissionEditPageData(
        request=request,
        course=edit_objects.course,
        homework=edit_objects.homework,
        submission=edit_objects.submission,
        questions=questions,
        questions_with_answers=questions_with_answers,
    )

    if request.method == "POST":
        response = handle_homework_submission_edit_post(edit_data)
        if response is not None:
            return response

    context = homework_submission_edit_context(edit_data)
    response = render(
        request, "cadmin/homework_submission_edit.html", context
    )
    return response


def homework_submission_edit_objects(
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


def questions_with_submission_answers(homework, submission):
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
    return questions, questions_with_answers


def handle_homework_submission_edit_post(data):
    form = HomeworkSubmissionEditForm(
        data.request.POST,
        submission=data.submission,
        questions=data.questions,
    )

    if not form.is_valid():
        error_message = first_form_error(form)
        messages.error(
            data.request,
            f"Error updating submission: {error_message}",
        )
        return None

    try:
        update_homework_submission_from_admin(
            data.submission,
            form.cleaned_data,
        )
    except Exception as e:
        messages.error(data.request, f"Error updating submission: {e}")
        return None

    return homework_submission_edit_success(data)


def homework_submission_edit_success(data):
    messages.success(
        data.request,
        f"Homework submission for {data.submission.student.username} updated successfully",
    )
    response = redirect(
        "cadmin_homework_submissions",
        course_slug=data.course.slug,
        homework_slug=data.homework.slug,
    )
    return response


def homework_submission_edit_context(data):
    if data.request.method == "POST":
        faq_contribution_url = data.request.POST.get(
            "faq_contribution_url", ""
        ).strip()
        faq_score = data.request.POST.get(
            "faq_score", data.submission.faq_score
        )
    else:
        faq_contribution_url = data.submission.faq_contribution_url or ""
        faq_score = data.submission.faq_score

    learning_in_public_links = data.submission.learning_in_public_links or []
    learning_in_public_links_text = "\n".join(learning_in_public_links)
    return {
        "course": data.course,
        "homework": data.homework,
        "submission": data.submission,
        "questions_with_answers": data.questions_with_answers,
        "learning_in_public_links_text": learning_in_public_links_text,
        "faq_contribution_url": faq_contribution_url,
        "faq_score": faq_score,
    }
