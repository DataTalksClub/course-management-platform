from django.contrib import messages
from django.shortcuts import redirect

from courses.models.homework import Submission
from courses.models.project import ProjectSubmission
from courses.services.enrollment_flags import (
    set_learning_in_public_disabled,
)


def toggle_learning_in_public_response(request, course, enrollment):
    disabled = not enrollment.disable_learning_in_public
    set_learning_in_public_disabled(enrollment, disabled)
    enrollment.disable_learning_in_public = disabled

    if enrollment.disable_learning_in_public:
        messages.success(
            request,
            f"Learning in public disabled for {enrollment.student.username}. All scores zeroed out.",
        )
    else:
        messages.success(
            request,
            f"Learning in public re-enabled for {enrollment.student.username}. You may need to re-score homework and projects.",
        )

    response = redirect(
        "cadmin_enrollment_edit",
        course_slug=course.slug,
        enrollment_id=enrollment.id,
    )
    return response


def enrollment_homework_submissions(enrollment):
    return (
        Submission.objects.filter(enrollment=enrollment)
        .select_related("homework")
        .order_by("-submitted_at")
    )


def enrollment_project_submissions(enrollment):
    return (
        ProjectSubmission.objects.filter(enrollment=enrollment)
        .select_related("project")
        .order_by("-submitted_at")
    )


def total_project_lip_score(project_submissions):
    total_score = 0
    for submission in project_submissions:
        project_score = submission.project_learning_in_public_score
        peer_review_score = submission.peer_review_learning_in_public_score
        total_score += project_score + peer_review_score
    return total_score


def total_homework_lip_score(homework_submissions):
    total_score = 0
    for submission in homework_submissions:
        total_score += submission.learning_in_public_score
    return total_score


def enrollment_edit_context(course, enrollment):
    homework_submissions = enrollment_homework_submissions(enrollment)
    project_submissions = enrollment_project_submissions(enrollment)
    homework_submissions_count = homework_submissions.count()
    project_submissions_count = project_submissions.count()
    total_homework_score = total_homework_lip_score(homework_submissions)
    total_project_score = total_project_lip_score(project_submissions)
    return {
        "course": course,
        "enrollment": enrollment,
        "homework_submissions": homework_submissions,
        "homework_submissions_count": homework_submissions_count,
        "project_submissions": project_submissions,
        "project_submissions_count": project_submissions_count,
        "total_homework_lip_score": total_homework_score,
        "total_project_lip_score": total_project_score,
    }
