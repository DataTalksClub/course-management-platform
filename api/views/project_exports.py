"""
Project-related data API views.

Provides views for retrieving project submission data.
"""

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.forms.models import model_to_dict
from django.views.decorators.http import require_GET

from accounts.auth import token_required

from courses.models import (
    Course,
    Project,
    ProjectSubmission,
)


def project_export_course_data(course):
    return model_to_dict(
        course, exclude=["students", "first_homework_scored"]
    )


def project_export_submission_data(submission):
    return {
        "student_id": submission.student_id,
        "student_email": submission.student.email,
        "github_link": submission.github_link,
        "commit_id": submission.commit_id,
        "learning_in_public_links": submission.learning_in_public_links,
        "faq_contribution_url": submission.faq_contribution_url,
        "time_spent": submission.time_spent,
        "problems_comments": submission.problems_comments,
        "project_score": submission.project_score,
        "project_faq_score": submission.project_faq_score,
        "project_learning_in_public_score": (
            submission.project_learning_in_public_score
        ),
        "peer_review_score": submission.peer_review_score,
        "peer_review_learning_in_public_score": (
            submission.peer_review_learning_in_public_score
        ),
        "total_score": submission.total_score,
        "reviewed_enough_peers": submission.reviewed_enough_peers,
        "passed": submission.passed,
    }


def project_export_project_data(project):
    project_data = model_to_dict(project)
    project_data["points_to_pass"] = project.points_to_pass
    return project_data


def project_export_payload(course, project, submissions):
    submission_records = []
    for submission in submissions:
        submission_record = project_export_submission_data(submission)
        submission_records.append(submission_record)

    return {
        "course": project_export_course_data(course),
        "project": project_export_project_data(project),
        "submissions": submission_records,
    }


@require_GET
@token_required
def project_data_view(request, course_slug: str, project_slug: str):
    """Get project data including course info, project details, and all submissions with scores."""
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )

    submissions = (
        ProjectSubmission.objects.filter(project=project)
        .prefetch_related("student", "enrollment")
        .all()
    )

    return JsonResponse(project_export_payload(course, project, submissions))
