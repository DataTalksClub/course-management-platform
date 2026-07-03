from dataclasses import dataclass

from django.shortcuts import get_object_or_404, render

from courses.models.course import Course
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
    student_submissions = ProjectSubmission.objects.filter(
        project=project,
        student=user,
    )
    project_submissions = student_submissions.filter(
        volunteer_review_only=False,
    )
    reviews = PeerReview.objects.filter(
        reviewer__in=student_submissions,
        submission_under_evaluation__project=project,
    ).select_related(
        "submission_under_evaluation__enrollment",
    ).order_by("optional")
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
        context = {
            "course": course,
            "project": project,
            "is_authenticated": False,
            "eval_closed": eval_closed,
        }
    else:
        context = student_project_eval_context(
            course,
            project,
            user,
            eval_closed,
        )

    response = render(request, "projects/eval.html", context)
    return response
