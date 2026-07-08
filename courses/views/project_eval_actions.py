from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect

from course_management.observability import record_event
from courses.models.course import Course, Enrollment
from courses.models.project import PeerReview, Project, ProjectSubmission


def volunteer_review_submission_defaults():
    github_link = (
        "https://github.com/DataTalksClub/course-management-platform"
    )
    defaults = {
        "github_link": github_link,
        "commit_id": "volunteer",
    }
    return defaults


def _project_eval_student_submission(course, project, user):
    student_submission = ProjectSubmission.objects.filter(
        project=project,
        student=user,
        volunteer_review_only=False,
    ).first()

    if student_submission is not None:
        return student_submission

    enrollment, _ = Enrollment.objects.get_or_create(
        student=user,
        course=course,
    )
    defaults = volunteer_review_submission_defaults()
    defaults["enrollment"] = enrollment
    student_submission, _ = ProjectSubmission.objects.get_or_create(
        project=project,
        student=user,
        volunteer_review_only=True,
        defaults=defaults,
    )
    return student_submission


def _create_optional_peer_review_if_allowed(
    course,
    project,
    user,
    submission_id,
):
    student_submission = _project_eval_student_submission(
        course,
        project,
        user,
    )

    if student_submission.id == submission_id:
        return

    submission_under_evaluation = ProjectSubmission.objects.get(
        id=submission_id,
        project=project,
        volunteer_review_only=False,
    )
    review, created = PeerReview.objects.get_or_create(
        submission_under_evaluation=submission_under_evaluation,
        reviewer=student_submission,
        optional=True,
    )
    return review, created


@login_required
def projects_eval_add(
    request, course_slug, project_slug, submission_id
):
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )
    result = _create_optional_peer_review_if_allowed(
        course,
        project,
        request.user,
        submission_id,
    )
    if result is not None:
        review, created = result
        record_event(
            "project.optional_review_added",
            request=request,
            properties={
                "course_slug": course.slug,
                "project_slug": project.slug,
                "project_id": project.id,
                "review_id": review.id,
                "submission_id": submission_id,
                "created": created,
            },
        )

    response = redirect(
        "project_list",
        course_slug=course.slug,
        project_slug=project.slug,
    )
    return response


@login_required
def projects_eval_delete(request, course_slug, project_slug, review_id):
    project = get_object_or_404(
        Project, course__slug=course_slug, slug=project_slug
    )

    user = request.user

    student_submission = get_object_or_404(
        ProjectSubmission,
        project=project,
        student=user,
    )

    deleted_count, _ = PeerReview.objects.filter(
        id=review_id,
        reviewer=student_submission,
        optional=True,
    ).delete()
    if deleted_count:
        record_event(
            "project.optional_review_deleted",
            request=request,
            properties={
                "course_slug": course_slug,
                "project_slug": project_slug,
                "project_id": project.id,
                "review_id": review_id,
            },
        )

    response = redirect(
        "projects_eval",
        course_slug=course_slug,
        project_slug=project_slug,
    )
    return response
