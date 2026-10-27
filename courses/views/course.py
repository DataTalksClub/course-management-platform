from django.conf import settings
from django.core.cache import cache
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


def _public_page_cache_allowed(request: HttpRequest) -> bool:
    return (
        request.method == "GET"
        and not request.user.is_authenticated
        and getattr(settings, "PUBLIC_PAGE_CACHE_ENABLED", True)
    )


def course_view(request: HttpRequest, course_slug: str) -> HttpResponse:
    if _public_page_cache_allowed(request):
        cache_key = f"course:anon:{course_slug}:v1"
        context = cache.get(cache_key)
        if context is None:
            data = course_page_data(course_slug, request.user)
            context = course_page_context(data)
            cache.set(
                cache_key,
                context,
                getattr(settings, "COURSE_ANON_CACHE_TTL", 60),
            )
        response = render(request, "courses/course.html", context)
        response["Cache-Control"] = (
            f"public, max-age={getattr(settings, 'COURSE_ANON_CACHE_TTL', 60)}"
        )
        return response
    data = course_page_data(course_slug, request.user)
    context = course_page_context(data)
    response = render(request, "courses/course.html", context)
    response["Cache-Control"] = "private, max-age=0, must-revalidate"
    return response
