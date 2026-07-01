import logging

from django.http import HttpRequest

from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect
from django.core.exceptions import ValidationError

from courses.models import (
    Course,
    Project,
)
from courses.views.project_page_context import (
    project_accepting_submissions,
    project_build_context,
)
from courses.views.project_submission_edit import (
    project_delete_submission,
    project_submission_from_post,
    project_submit_post,
)
logger = logging.getLogger(__name__)

PROJECT_SUBMISSION_DELETED_MESSAGE = (
    "Your project submission is deleted. You can still make a new submission if you want."
)
PROJECT_SUBMISSION_SAVED_MESSAGE = (
    "Thank you for submitting your project, it is now saved. You can update your submission at any point before the due date."
)


def project_login_required_response(
    request: HttpRequest, course: Course, project: Project
):
    messages.error(
        request,
        "You need to be logged in to submit a project",
        extra_tags="homework",
    )
    response = redirect(
        "project",
        course_slug=course.slug,
        project_slug=project.slug,
    )
    return response


def closed_project_submission_response(
    request: HttpRequest, course: Course, project: Project
):
    messages.error(
        request,
        "Project submission form is closed.",
        extra_tags="homework",
    )
    context = project_build_context(request, course, project)
    response = render(request, "projects/project.html", context)
    return response


def is_delete_project_submission_request(request: HttpRequest) -> bool:
    return "action" in request.POST and request.POST["action"] == "delete"


def project_validation_error_response(
    request: HttpRequest,
    course: Course,
    project: Project,
    error: ValidationError,
):
    error_messages = error.messages
    for message in error_messages:
        messages.error(
            request,
            f"Failed to submit the project: {message}",
            extra_tags="alert-danger",
        )
    context = project_build_context(request, course, project)
    context["submission"] = project_submission_from_post(request, project)
    response = render(request, "projects/project.html", context)
    return response


def handle_project_post(request: HttpRequest, course: Course, project: Project):
    if not request.user.is_authenticated:
        return project_login_required_response(request, course, project)

    if not project_accepting_submissions(project):
        return closed_project_submission_response(
            request, course, project
        )

    if is_delete_project_submission_request(request):
        project_delete_submission(request, project)
        messages.success(
            request,
            PROJECT_SUBMISSION_DELETED_MESSAGE,
            extra_tags="homework",
        )
    else:
        try:
            project_submit_post(request, project)
            messages.success(
                request,
                PROJECT_SUBMISSION_SAVED_MESSAGE,
                extra_tags="homework",
            )
        except ValidationError as error:
            return project_validation_error_response(
                request, course, project, error
            )

    response = redirect(
        "project",
        course_slug=course.slug,
        project_slug=project.slug,
    )
    return response


def project_view(request, course_slug, project_slug):
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )

    if request.method == "POST":
        return handle_project_post(
            request,
            course,
            project,
        )

    context = project_build_context(request, course, project)

    response = render(request, "projects/project.html", context)
    return response
