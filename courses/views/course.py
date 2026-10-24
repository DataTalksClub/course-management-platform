from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from courses.models.course import Course
from courses.views.course_page_context import (
    course_page_context,
    course_page_data,
)


def legacy_course_redirect(
    request: HttpRequest, course_slug: str
) -> HttpResponse:
    course = get_object_or_404(Course, slug=course_slug)
    return redirect("course", course_slug=course.slug, permanent=True)


def course_view(request: HttpRequest, course_slug: str) -> HttpResponse:
    data = course_page_data(course_slug, request.user)
    context = course_page_context(data)
    return render(request, "courses/course.html", context)
