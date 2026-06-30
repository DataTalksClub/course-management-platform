"""
Homework-related data API views.

Provides views for retrieving homework submission data.
"""

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.db.models import Prefetch
from django.forms.models import model_to_dict
from django.views.decorators.http import require_GET

from accounts.auth import token_required

from courses.models import (
    Course,
    Homework,
    Answer,
)


def homework_export_course_data(course):
    return model_to_dict(
        course, exclude=["students", "first_homework_scored"]
    )


def homework_export_submission_answers(submission):
    answer_values = submission.answer_set.values(
        "question_id", "answer_text", "is_correct"
    )
    return list(answer_values)


def homework_export_submission_data(submission):
    answers = homework_export_submission_answers(submission)
    return {
        "student_id": submission.student_id,
        "homework_link": submission.homework_link,
        "learning_in_public_links": submission.learning_in_public_links,
        "time_spent_lectures": submission.time_spent_lectures,
        "time_spent_homework": submission.time_spent_homework,
        "problems_comments": submission.problems_comments,
        "faq_contribution_url": submission.faq_contribution_url,
        "questions_score": submission.questions_score,
        "faq_score": submission.faq_score,
        "learning_in_public_score": submission.learning_in_public_score,
        "total_score": submission.total_score,
        "answers": answers,
    }


def homework_export_submissions(homework):
    answers_queryset = Answer.objects.all()
    answers_prefetch = Prefetch(
        "answer_set", queryset=answers_queryset
    )
    submissions = homework.submission_set.prefetch_related(answers_prefetch)
    all_submissions = submissions.all()
    return all_submissions


def homework_export_payload(course, homework, submissions):
    submission_records = []
    for submission in submissions:
        submission_record = homework_export_submission_data(submission)
        submission_records.append(submission_record)

    course_data = homework_export_course_data(course)
    homework_data = model_to_dict(homework)
    return {
        "course": course_data,
        "homework": homework_data,
        "submissions": submission_records,
    }


@require_GET
@token_required
def homework_data_view(request, course_slug: str, homework_slug: str):
    """Get homework data including course info, homework details, and all submissions with answers."""
    course = get_object_or_404(Course, slug=course_slug)

    homework = get_object_or_404(
        Homework, course=course, slug=homework_slug
    )
    submissions = homework_export_submissions(homework)

    payload = homework_export_payload(course, homework, submissions)
    return JsonResponse(payload)
