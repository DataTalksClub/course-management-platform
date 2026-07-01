from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from courses.assignment_statistics import calculate_project_statistics
from courses.models.course import Course
from courses.models.project import Project, ProjectState


def incomplete_project_statistics_response(request, course, project):
    messages.error(
        request,
        "This project is not completed yet, so there are no available statistics.",
        extra_tags="project",
    )
    response = redirect(
        "project",
        course_slug=course.slug,
        project_slug=project.slug,
    )
    return response


def project_statistics(request, course_slug, project_slug):
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )

    if project.state != ProjectState.COMPLETED.value:
        return incomplete_project_statistics_response(
            request,
            course,
            project,
        )

    stats = calculate_project_statistics(project, force=False)

    context = {
        "course": course,
        "project": project,
        "stats": stats,
    }

    response = render(request, "projects/stats.html", context)
    return response
