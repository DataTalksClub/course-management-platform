from dataclasses import dataclass

from django.core.paginator import Page
from django.db.models import Q
from django.http import HttpRequest

from courses.models import Course, Homework, Submission
from cadmin.views.helpers import pagination_querystring


@dataclass(frozen=True)
class HomeworkSubmissionsContextData:
    request: HttpRequest
    course: Course
    homework: Homework
    submissions_page: Page
    search_query: str


def homework_submissions_queryset(homework, search_query):
    submissions = (
        Submission.objects.filter(homework=homework)
        .select_related("student", "enrollment")
        .order_by("-submitted_at")
    )

    if search_query:
        submissions = submissions.filter(
            Q(student__email__icontains=search_query)
            | Q(student__username__icontains=search_query)
        )
    return submissions


def homework_submissions_context(data):
    submissions_data = homework_submissions_data(
        data.submissions_page.object_list
    )
    querystring = pagination_querystring(data.request)
    return {
        "course": data.course,
        "homework": data.homework,
        "submissions_data": submissions_data,
        "submissions_page": data.submissions_page,
        "search_query": data.search_query,
        "pagination_querystring": querystring,
    }


def homework_submissions_data(submissions):
    submissions_data = []
    for submission in submissions:
        record = {"submission": submission}
        submissions_data.append(record)
    return submissions_data
