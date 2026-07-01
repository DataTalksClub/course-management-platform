from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from courses.models import (
    Course,
    PeerReview,
    Project,
    ProjectState,
    ReviewCriteria,
)
from courses.votes import (
    update_project_vote,
)
from courses.views.project_eval_submit_context import (
    ProjectEvalSubmitPage,
    project_eval_submit_context,
)
from courses.views.project_eval_submit_save import (
    project_eval_post_submission,
)


def project_eval_vote_response(request, course_slug, project_slug, review):
    action = request.POST.get("action", "vote")
    update_project_vote(
        request.user,
        review.submission_under_evaluation,
        action=action,
    )
    response = redirect(
        "projects_eval_submit",
        course_slug=course_slug,
        project_slug=project_slug,
        review_id=review.id,
    )
    return response


def closed_project_eval_response(
    request,
    page: ProjectEvalSubmitPage,
):
    messages.error(
        request,
        "Peer review form is closed.",
        extra_tags="homework",
    )
    context = project_eval_submit_context(request, page)
    response = render(request, "projects/eval_submit.html", context)
    return response


def project_eval_submission_response(
    request,
    page: ProjectEvalSubmitPage,
):
    project_eval_post_submission(
        request,
        page.project,
        page.review,
        page.review_criteria,
    )
    response = redirect(
        "projects_eval",
        course_slug=page.course.slug,
        project_slug=page.project.slug,
    )
    return response


def projects_eval_submit_post_response(
    request,
    page: ProjectEvalSubmitPage,
):
    if request.POST.get("form_action") == "vote":
        return project_eval_vote_response(
            request,
            page.course.slug,
            page.project.slug,
            page.review,
        )

    if page.project.state != ProjectState.PEER_REVIEWING.value:
        return closed_project_eval_response(
            request,
            page,
        )

    response = project_eval_submission_response(
        request,
        page,
    )
    return response


def project_eval_submit_page(
    course_slug,
    project_slug,
    review,
) -> ProjectEvalSubmitPage:
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, slug=project_slug, course=course
    )
    review_criteria = ReviewCriteria.objects.filter(
        course=course
    ).order_by("id")
    return ProjectEvalSubmitPage(
        course=course,
        project=project,
        review=review,
        review_criteria=review_criteria,
    )


def project_eval_unauthorized_response(
    request,
    course_slug,
    project_slug,
):
    messages.error(
        request,
        "You are not allowed to evaluate this submission, choose a different one.",
        extra_tags="homework",
    )
    response = redirect(
        "projects_eval",
        course_slug=course_slug,
        project_slug=project_slug,
    )
    return response


@login_required
def projects_eval_submit(request, course_slug, project_slug, review_id):
    review = get_object_or_404(PeerReview, id=review_id)

    if review.reviewer.student != request.user:
        response = project_eval_unauthorized_response(
            request,
            course_slug,
            project_slug,
        )
        return response

    page = project_eval_submit_page(course_slug, project_slug, review)

    if request.method == "POST":
        return projects_eval_submit_post_response(
            request,
            page,
        )

    context = project_eval_submit_context(
        request,
        page,
    )

    response = render(request, "projects/eval_submit.html", context)
    return response
