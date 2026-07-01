from django.shortcuts import get_object_or_404, redirect, render

from courses.models.course import Course
from courses.views.dashboard_context import dashboard_context


def dashboard_view(request, course_slug: str):
    course = get_object_or_404(Course, slug=course_slug)
    if not course.first_homework_scored:
        response = redirect("course", course_slug=course.slug)
        return response

    context = dashboard_context(course)
    response = render(
        request,
        "courses/dashboard.html",
        context,
    )
    return response
