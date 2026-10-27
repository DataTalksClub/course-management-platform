from django.conf import settings
from django.core.cache import cache
from django.shortcuts import get_object_or_404, redirect, render

from courses.models.course import Course
from courses.views.dashboard_context import dashboard_context


def dashboard_view(request, course_slug: str):
    course = get_object_or_404(Course, slug=course_slug)
    if not course.first_homework_scored:
        response = redirect("course", course_slug=course.slug)
        return response

    if getattr(settings, "PUBLIC_PAGE_CACHE_ENABLED", True):
        cache_key = f"dashboard:{course.id}:v1"
        context = cache.get(cache_key)
        if context is None:
            context = dashboard_context(course)
            cache.set(
                cache_key,
                context,
                getattr(settings, "DASHBOARD_CACHE_TTL", 300),
            )
        response = render(
            request,
            "courses/dashboard.html",
            context,
        )
        response["Cache-Control"] = (
            "public, max-age="
            f"{getattr(settings, 'DASHBOARD_CACHE_TTL', 300)}"
        )
        return response

    context = dashboard_context(course)
    response = render(
        request,
        "courses/dashboard.html",
        context,
    )
    return response
