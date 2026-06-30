from django.core.paginator import Paginator
from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.shortcuts import get_object_or_404, render

from courses.models.course import Course
from courses.models.project import Project, ProjectState, ProjectSubmission

PROJECT_SUBMISSIONS_PAGE_SIZE = 25


def list_all_project_submissions_view(request, course_slug: str):
    course = get_object_or_404(Course, slug=course_slug)
    submissions_page = _all_project_submissions_page(course, request)
    projects = _projects_with_submission_counts(course)
    context = _all_project_submissions_context(
        course,
        projects,
        submissions_page,
        request.user,
    )

    return render(request, "projects/list_all.html", context)


def _projects_with_submission_counts(course):
    return (
        Project.objects.filter(course=course)
        .annotate(
            submissions_count=Count(
                "projectsubmission",
                filter=Q(projectsubmission__volunteer_review_only=False),
            )
        )
        .order_by("id")
    )


def _all_project_submissions(course):
    return (
        ProjectSubmission.objects.filter(
            project__course=course,
            volunteer_review_only=False,
        )
        .select_related("project", "enrollment")
        .annotate(
            vote_count=Count("votes"),
            display_score=_project_submission_display_score(),
        )
        .order_by(
            "-vote_count",
            "-display_score",
            "project__id",
            "submitted_at",
        )
    )


def _project_submission_display_score():
    completed_project_score = When(
        project__state=ProjectState.COMPLETED.value,
        then="project_score",
    )
    unscored_project_score = Value(-1)
    output_field = IntegerField()
    return Case(
        completed_project_score,
        default=unscored_project_score,
        output_field=output_field,
    )


def _all_project_submissions_page(course, request):
    submissions = _all_project_submissions(course)
    paginator = Paginator(submissions, PROJECT_SUBMISSIONS_PAGE_SIZE)
    page_number = request.GET.get("page")
    return paginator.get_page(page_number)


def _all_project_submissions_context(
    course,
    projects,
    submissions_page,
    user,
):
    page_range = submissions_page.paginator.get_elided_page_range(
        submissions_page.number
    )
    return {
        "course": course,
        "projects": projects,
        "submissions": submissions_page.object_list,
        "submissions_page": submissions_page,
        "page_range": page_range,
        "is_authenticated": user.is_authenticated,
    }
