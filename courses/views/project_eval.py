from dataclasses import dataclass

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from courses.models.course import Course, Enrollment
from courses.models.project import (
    PeerReview,
    PeerReviewState,
    Project,
    ProjectState,
    ProjectSubmission,
)


@dataclass(frozen=True)
class ProjectEvalReviewGroups:
    assigned_reviews: list
    selected_reviews: list
    completed_count: int


def anonymous_project_eval_context(course, project, eval_closed):
    return {
        "course": course,
        "project": project,
        "is_authenticated": False,
        "eval_closed": eval_closed,
    }


def student_project_submissions(project, user):
    return ProjectSubmission.objects.filter(project=project, student=user)


def project_eval_reviews(project, student_submissions):
    return PeerReview.objects.filter(
        reviewer__in=student_submissions,
        submission_under_evaluation__project=project,
    ).order_by("optional")


def split_project_eval_reviews(reviews):
    assigned_reviews = []
    selected_reviews = []
    completed_count = 0

    for review in reviews:
        if review.optional:
            selected_reviews.append(review)
            continue
        assigned_reviews.append(review)
        if review.state == PeerReviewState.SUBMITTED.value:
            completed_count += 1

    return ProjectEvalReviewGroups(
        assigned_reviews=assigned_reviews,
        selected_reviews=selected_reviews,
        completed_count=completed_count,
    )


def student_project_eval_context(course, project, user, eval_closed):
    student_submissions = student_project_submissions(project, user)
    project_submissions = student_submissions.filter(
        volunteer_review_only=False,
    )
    reviews = project_eval_reviews(project, student_submissions)
    review_groups = split_project_eval_reviews(reviews)
    has_submission = project_submissions.exists()

    return {
        "course": course,
        "project": project,
        "reviews": reviews,
        "assigned_reviews": review_groups.assigned_reviews,
        "selected_reviews": review_groups.selected_reviews,
        "is_authenticated": True,
        "number_of_completed_evaluation": review_groups.completed_count,
        "has_submission": has_submission,
        "eval_closed": eval_closed,
    }


def projects_eval_view(request, course_slug, project_slug):
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )

    user = request.user
    is_authenticated = user.is_authenticated
    eval_closed = project.state != ProjectState.PEER_REVIEWING.value

    if not is_authenticated:
        context = anonymous_project_eval_context(
            course,
            project,
            eval_closed,
        )
    else:
        context = student_project_eval_context(
            course,
            project,
            user,
            eval_closed,
        )

    response = render(request, "projects/eval.html", context)
    return response


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
    student_submission, _ = ProjectSubmission.objects.get_or_create(
        project=project,
        student=user,
        volunteer_review_only=True,
        defaults={
            "enrollment": enrollment,
            "github_link": (
                "https://github.com/DataTalksClub/"
                "course-management-platform"
            ),
            "commit_id": "volunteer",
        },
    )
    return student_submission


def _submission_under_project_evaluation(project, submission_id):
    return ProjectSubmission.objects.get(
        id=submission_id,
        project=project,
        volunteer_review_only=False,
    )


def _create_optional_peer_review(
    student_submission,
    submission_under_evaluation,
):
    PeerReview.objects.get_or_create(
        submission_under_evaluation=submission_under_evaluation,
        reviewer=student_submission,
        optional=True,
    )


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

    submission_under_evaluation = _submission_under_project_evaluation(
        project,
        submission_id,
    )
    _create_optional_peer_review(
        student_submission,
        submission_under_evaluation,
    )


@login_required
def projects_eval_add(
    request, course_slug, project_slug, submission_id
):
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )
    _create_optional_peer_review_if_allowed(
        course,
        project,
        request.user,
        submission_id,
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

    PeerReview.objects.filter(
        id=review_id,
        reviewer=student_submission,
        optional=True,
    ).delete()

    response = redirect(
        "projects_eval",
        course_slug=course_slug,
        project_slug=project_slug,
    )
    return response
