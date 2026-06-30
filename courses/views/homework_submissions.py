from django.contrib import messages
from django.http import HttpRequest
from django.shortcuts import redirect


def homework_submissions(
    request: HttpRequest,
    course_slug: str,
    homework_slug: str,
):
    user = request.user

    if not user.is_authenticated or not user.is_staff:
        messages.error(
            request,
            "You do not have permission to view this page.",
            extra_tags="homework",
        )
        response = redirect(
            "homework",
            course_slug=course_slug,
            homework_slug=homework_slug,
        )
        return response

    response = redirect(
        "cadmin_homework_submissions",
        course_slug=course_slug,
        homework_slug=homework_slug,
    )
    return response
