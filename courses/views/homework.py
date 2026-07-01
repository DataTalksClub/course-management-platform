from dataclasses import dataclass

from django.http import HttpRequest

from django.shortcuts import render

from courses.models.course import Course
from courses.models.homework import (
    Homework,
    Question,
)
from courses.views.homework_context import (
    AuthenticatedHomeworkContext,
    authenticated_homework_context,
    homework_detail_build_context_not_authenticated,
    homework_detail_objects,
)
from courses.views.homework_post_preview import (
    handle_homework_post,
)
from courses.views.homework_submission import (
    HomeworkPostData,
)


@dataclass(frozen=True)
class HomeworkRequestData:
    request: HttpRequest
    course: Course
    homework: Homework
    questions: list[Question]


def authenticated_homework_response(data: HomeworkRequestData):
    authenticated_context = authenticated_homework_context(
        user=data.request.user,
        course=data.course,
        homework=data.homework,
        questions=data.questions,
    )

    if data.request.method != "POST":
        response = render(
            data.request,
            "homework/homework.html",
            authenticated_context.context,
        )
        return response

    return authenticated_homework_post_response(
        data,
        authenticated_context,
    )


def authenticated_homework_post_response(
    data: HomeworkRequestData,
    authenticated_context: AuthenticatedHomeworkContext,
):
    post_data = HomeworkPostData(
        request=data.request,
        course=data.course,
        homework=data.homework,
        questions=data.questions,
        submission=authenticated_context.submission,
        enrollment=authenticated_context.enrollment,
    )
    post_result = handle_homework_post(post_data)
    if not isinstance(post_result, dict):
        return post_result

    response = render(data.request, "homework/homework.html", post_result)
    return response


def homework_view(
    request: HttpRequest, course_slug: str, homework_slug: str
):
    detail_objects = homework_detail_objects(
        course_slug,
        homework_slug,
    )
    course = detail_objects.course
    homework = detail_objects.homework
    questions = detail_objects.questions
    user = request.user

    if not user.is_authenticated:
        context = homework_detail_build_context_not_authenticated(
            course=course, homework=homework, questions=questions
        )
        response = render(request, "homework/homework.html", context)
        return response

    request_data = HomeworkRequestData(
        request=request,
        course=course,
        homework=homework,
        questions=questions,
    )
    return authenticated_homework_response(request_data)
