from django.core.paginator import Paginator
from django.db.models import Count

from courses.models.project import (
    ProjectState,
    ProjectSubmission,
)
from courses.views.project_submission_display import (
    ProjectSubmissionsDecorationData,
    apply_project_group_headings,
    decorate_project_submissions,
    sort_project_submissions_for_view,
)
from courses.votes import PROJECT_VOTES_PER_PROJECT


PROJECT_SUBMISSIONS_PAGE_SIZE = 25


def project_submissions_page(request, project, viewer_state):
    submissions = _project_submissions_queryset(project)
    submissions_list = list(submissions)
    decoration_data = ProjectSubmissionsDecorationData(
        submissions_list=submissions_list,
        project=project,
        viewer_state=viewer_state,
    )
    decorate_project_submissions(decoration_data)
    sort_project_submissions_for_view(
        submissions_list,
        project=project,
        viewer_state=viewer_state,
    )

    submissions_page = paginate_project_submissions(
        request, submissions_list
    )
    apply_project_group_headings(submissions_page)
    return submissions_page


def projects_list_context(course, project, submissions_page, viewer_state):
    page_range = submissions_page.paginator.get_elided_page_range(
        submissions_page.number
    )

    return {
        "course": course,
        "project": project,
        "submissions": submissions_page.object_list,
        "submissions_page": submissions_page,
        "page_range": page_range,
        "is_authenticated": viewer_state.is_authenticated,
        "has_submission": viewer_state.has_submission,
        "voted_submission_ids": viewer_state.voted_submission_ids,
        "project_votes_per_project": PROJECT_VOTES_PER_PROJECT,
        "project_votes_left": viewer_state.project_votes_left,
    }


def paginate_project_submissions(request, submissions):
    paginator = Paginator(submissions, PROJECT_SUBMISSIONS_PAGE_SIZE)
    page_number = request.GET.get("page")
    return paginator.get_page(page_number)


def _project_submissions_queryset(project):
    submissions = ProjectSubmission.objects.filter(
        project=project,
        volunteer_review_only=False,
    )
    submissions = submissions.select_related("enrollment")
    vote_count_annotation = Count("votes")
    submissions = submissions.annotate(vote_count=vote_count_annotation)

    if project.state == ProjectState.COMPLETED.value:
        return submissions.order_by("-project_score")

    return submissions.order_by("-submitted_at")
