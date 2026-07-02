from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest
from django.shortcuts import redirect

from courses.models.course import Course
from courses.models.homework import (
    Homework,
    HomeworkState,
)
from courses.views.homework_post_context import homework_validation_context
from courses.views.homework_submission import (
    HomeworkPostData,
    process_homework_submission,
)


def closed_homework_submission_response(
    request: HttpRequest,
    course: Course,
    homework: Homework,
):
    messages.error(
        request,
        "This homework is not open for submissions.",
        extra_tags="homework",
    )
    response = redirect(
        "homework",
        course_slug=course.slug,
        homework_slug=homework.slug,
    )
    return response


def handle_homework_post(data: HomeworkPostData):
    if data.homework.state != HomeworkState.OPEN.value:
        return closed_homework_submission_response(
            data.request,
            data.course,
            data.homework,
        )

    try:
        with transaction.atomic():
            return process_homework_submission(data)
    except ValidationError as error:
        return homework_validation_context(
            data=data,
            error=error,
        )
