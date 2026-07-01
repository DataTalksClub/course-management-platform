from django.http import HttpRequest

from courses.models.course import Course
from courses.models.homework import Homework, Submission


def post_preview_value(request: HttpRequest, key: str) -> str:
    return request.POST.get(key, "")


def post_preview_learning_links(request: HttpRequest) -> list[str]:
    links = []
    raw_links = request.POST.getlist("learning_in_public_links[]")
    for raw_link in raw_links:
        link = raw_link.strip()
        if link:
            links.append(link)
    return links


def apply_post_preview_homework_url(
    request: HttpRequest,
    homework: Homework,
    submission: Submission,
) -> None:
    if homework.homework_url_field:
        submission.homework_link = post_preview_value(
            request,
            "homework_url",
        )


def apply_post_preview_learning_links(
    request: HttpRequest,
    homework: Homework,
    submission: Submission,
) -> None:
    if homework.learning_in_public_cap > 0:
        submission.learning_in_public_links = (
            post_preview_learning_links(request)
        )


def apply_post_preview_time_spent(
    request: HttpRequest,
    homework: Homework,
    submission: Submission,
) -> None:
    if homework.time_spent_lectures_field:
        submission.time_spent_lectures = post_preview_value(
            request,
            "time_spent_lectures",
        )

    if homework.time_spent_homework_field:
        submission.time_spent_homework = post_preview_value(
            request,
            "time_spent_homework",
        )


def apply_post_preview_comments(
    request: HttpRequest,
    course: Course,
    submission: Submission,
) -> None:
    if course.homework_problems_comments_field:
        submission.problems_comments = post_preview_value(
            request,
            "problems_comments",
        )


def apply_post_preview_faq_contribution(
    request: HttpRequest,
    homework: Homework,
    submission: Submission,
) -> None:
    if homework.faq_contribution_field:
        submission.faq_contribution_url = post_preview_value(
            request,
            "faq_contribution_url",
        )


def apply_homework_post_preview_fields(
    request: HttpRequest,
    course: Course,
    homework: Homework,
    submission: Submission,
) -> None:
    apply_post_preview_homework_url(request, homework, submission)
    apply_post_preview_learning_links(request, homework, submission)
    apply_post_preview_time_spent(request, homework, submission)
    apply_post_preview_comments(request, course, submission)
    apply_post_preview_faq_contribution(request, homework, submission)
