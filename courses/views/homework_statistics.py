from django.contrib import messages
from django.http import HttpRequest
from django.shortcuts import get_object_or_404, redirect, render

from courses.assignment_statistics import calculate_homework_statistics
from courses.models import Course, Homework


def unscored_homework_statistics_response(
    request: HttpRequest,
    course: Course,
    homework: Homework,
):
    messages.error(
        request,
        "This homework is not scored yet, so there are no available statistics.",
        extra_tags="homework",
    )
    response = redirect(
        "homework",
        course_slug=course.slug,
        homework_slug=homework.slug,
    )
    return response


def scored_homework_statistics_response(
    request: HttpRequest,
    course: Course,
    homework: Homework,
):
    stats = calculate_homework_statistics(homework, force=False)
    context = {
        "course": course,
        "homework": homework,
        "stats": stats,
    }

    response = render(request, "homework/stats.html", context)
    return response


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
        response = unscored_homework_statistics_response(
            request,
            course,
            homework,
        )
        return response

    response = scored_homework_statistics_response(
        request,
        course,
        homework,
    )
    return response
