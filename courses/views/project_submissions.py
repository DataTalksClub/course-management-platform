from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from courses.models import (
    Course,
    Project,
)
from courses.views.project_submission_listing import (
    project_submissions_page,
    projects_list_context,
)
from courses.views.project_submission_viewer import project_viewer_state
from courses.views.project_submission_votes import (
    project_vote_response,
)


def projects_list_view(request, course_slug, project_slug):
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )

    if request.method == "POST":
        return project_vote_response(request, course, project)

    user = request.user
    viewer_state = project_viewer_state(project, course, user)
    submissions_page = project_submissions_page(
        request, project, viewer_state
    )
    context = projects_list_context(
        course, project, submissions_page, viewer_state
    )

    response = render(request, "projects/list.html", context)
    return response


def project_submissions(request, course_slug, project_slug):
    if not request.user.is_authenticated or not request.user.is_staff:
        messages.error(
            request,
            "You do not have permission to view this page.",
            extra_tags="project",
        )
        response = redirect(
            "project",
            course_slug=course_slug,
            project_slug=project_slug,
        )
        return response

    response = redirect(
        "cadmin_project_submissions",
        course_slug=course_slug,
        project_slug=project_slug,
    )
    return response
