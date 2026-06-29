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
    return list(
        submission.answer_set.values(
            "question_id", "answer_text", "is_correct"
        )
    )


def homework_export_submission_data(submission):
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
        "answers": homework_export_submission_answers(submission),
    }


def homework_export_submissions(homework):
    answers_prefetch = Prefetch(
        "answer_set", queryset=Answer.objects.all()
    )
    return homework.submission_set.prefetch_related(answers_prefetch).all()


def homework_export_payload(course, homework, submissions):
    return {
        "course": homework_export_course_data(course),
        "homework": model_to_dict(homework),
        "submissions": [
            homework_export_submission_data(submission)
            for submission in submissions
        ],
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

    return JsonResponse(homework_export_payload(course, homework, submissions))
