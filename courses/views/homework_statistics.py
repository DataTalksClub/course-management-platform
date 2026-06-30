from django.contrib import messages
from django.http import HttpRequest
from django.shortcuts import get_object_or_404, redirect, render

from courses.models import Course, Homework
from courses.scoring import calculate_homework_statistics


def homework_statistics(
    request: HttpRequest,
    course_slug: str,
    homework_slug: str,
):
    course = get_object_or_404(Course, slug=course_slug)
    homework = get_object_or_404(
        Homework,
        course=course,
        slug=homework_slug,
    )

    if not homework.is_scored():
        messages.error(
            request,
            "This homework is not scored yet, so there are no available statistics.",
            extra_tags="homework",
        )
        return redirect(
            "homework",
            course_slug=course.slug,
            homework_slug=homework.slug,
        )

    stats = calculate_homework_statistics(homework, force=False)
    context = {
        "course": course,
        "homework": homework,
        "stats": stats,
    }

    return render(request, "homework/stats.html", context)
