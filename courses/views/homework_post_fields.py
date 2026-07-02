from django.http import HttpRequest

from courses.models.course import Course
from courses.models.homework import Homework, Submission


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
        homework_url = request.POST.get("homework_url", "")
        submission.homework_link = homework_url


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
        time_spent_lectures = request.POST.get("time_spent_lectures", "")
        submission.time_spent_lectures = time_spent_lectures

    if homework.time_spent_homework_field:
        time_spent_homework = request.POST.get("time_spent_homework", "")
        submission.time_spent_homework = time_spent_homework


def apply_post_preview_comments(
    request: HttpRequest,
    course: Course,
    submission: Submission,
) -> None:
    if course.homework_problems_comments_field:
        problems_comments = request.POST.get("problems_comments", "")
        submission.problems_comments = problems_comments


def apply_post_preview_faq_contribution(
    request: HttpRequest,
    homework: Homework,
    submission: Submission,
) -> None:
    if homework.faq_contribution_field:
        faq_contribution_url = request.POST.get("faq_contribution_url", "")
        submission.faq_contribution_url = faq_contribution_url


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
