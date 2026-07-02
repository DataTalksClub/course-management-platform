from dataclasses import dataclass

from django.core.paginator import Page
from django.http import HttpRequest

from courses.models.course import Course
from courses.models.project import Project, ProjectState

from .helpers import paginate_queryset, pagination_querystring
from .view_models import project_submission_list_data

CADMIN_PROJECT_SUBMISSIONS_PAGE_SIZE = 50


@dataclass(frozen=True)
class ProjectSubmissionsContextData:
    request: HttpRequest
    course: Course
    project: Project
    submissions_page: Page
    project_filter_counts: dict
    search_query: str
    status_filter: str


def apply_project_action_flags(project):
    project.needs_review_assignment = (
        project.state == ProjectState.COLLECTING_SUBMISSIONS.value
    )
    project.needs_scoring = (
        project.state == ProjectState.PEER_REVIEWING.value
    )


def project_submissions_context(data):
    page_range = data.submissions_page.paginator.get_elided_page_range(
        data.submissions_page.number
    )
    querystring = pagination_querystring(data.request)
    return {
        "course": data.course,
        "project": data.project,
        "submissions": data.submissions_page.object_list,
        "submissions_page": data.submissions_page,
        "page_range": page_range,
        "project_filter_counts": data.project_filter_counts,
        "search_query": data.search_query,
        "status_filter": data.status_filter,
        "pagination_querystring": querystring,
    }


def project_submissions_request_filters(request):
    raw_search_query = request.GET.get("q", "")
    search_query = raw_search_query.strip()
    status_filter = request.GET.get("status", "all")
    return (
        search_query,
        status_filter,
    )


def project_submissions_page_data(request, course, project):
    search_query, status_filter = project_submissions_request_filters(
        request
    )
    submissions, project_filter_counts = project_submission_list_data(
        project,
        search_query,
        status_filter,
    )
    submissions_page = paginate_queryset(
        request,
        submissions,
        per_page=CADMIN_PROJECT_SUBMISSIONS_PAGE_SIZE,
    )
    return ProjectSubmissionsContextData(
        request=request,
        course=course,
        project=project,
        submissions_page=submissions_page,
        project_filter_counts=project_filter_counts,
        search_query=search_query,
        status_filter=status_filter,
    )
