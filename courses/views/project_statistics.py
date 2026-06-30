from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from courses.assignment_statistics import calculate_project_statistics
from courses.models import Course, Project, ProjectState


def project_statistics(request, course_slug, project_slug):
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )

    if project.state != ProjectState.COMPLETED.value:
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

    stats = calculate_project_statistics(project, force=False)

    context = {
        "course": course,
        "project": project,
        "stats": stats,
    }

    response = render(request, "projects/stats.html", context)
    return response
