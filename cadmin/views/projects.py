from dataclasses import dataclass

from django.contrib import messages
from django.core.paginator import Page
from django.http import HttpRequest
from django.shortcuts import get_object_or_404, redirect, render

from course_management.datamailer.sync import (
    send_peer_review_assignment_notification,
    send_project_score_notification,
)
from courses.models import (
    Course,
    Project,
    ProjectEvaluationScore,
    ProjectState,
    ProjectSubmission,
    ReviewCriteria,
)
from courses.project_assignment import (
    ProjectActionStatus,
    assign_peer_reviews_for_project,
)
from courses.projects import (
    score_project,
)
from cadmin.forms import ProjectSubmissionEditForm
from cadmin.services import update_project_submission_from_admin
from .helpers import (
    first_form_error,
    paginate_queryset,
    pagination_querystring,
    redirect_after_action,
    staff_required,
)
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


@dataclass(frozen=True)
class ProjectSubmissionEditPageData:
    request: HttpRequest
    course: Course
    project: Project
    submission: ProjectSubmission
    review_criteria: list
    criteria_with_scores: list


@dataclass(frozen=True)
class ProjectSubmissionEditObjects:
    course: Course
    project: Project
    submission: ProjectSubmission


@staff_required
def project_assign_reviews(request, course_slug, project_slug):
    """Assign peer reviews for a project"""
    if request.method != "POST":
        return redirect("cadmin_course", course_slug=course_slug)
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )

    status, message = assign_peer_reviews_for_project(project)

    if status == ProjectActionStatus.OK:
        messages.success(request, message)
        send_peer_review_assignment_notification(project)
    else:
        messages.warning(request, message)

    return redirect_after_action(
        request, "cadmin_course", course_slug=course_slug
    )


@staff_required
def project_score(request, course_slug, project_slug):
    """Score a project"""
    if request.method != "POST":
        return redirect("cadmin_course", course_slug=course_slug)
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )

    status, message = score_project(project)

    if status == ProjectActionStatus.OK:
        messages.success(request, message)
        send_project_score_notification(project)
    else:
        messages.warning(request, message)

    return redirect_after_action(
        request, "cadmin_course", course_slug=course_slug
    )


def _apply_project_action_flags(project):
    project.needs_review_assignment = (
        project.state == ProjectState.COLLECTING_SUBMISSIONS.value
    )
    project.needs_scoring = (
        project.state == ProjectState.PEER_REVIEWING.value
    )


def _project_submissions_context(data):
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


def _project_submissions_request_filters(request):
    search_query = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "all")
    return (
        search_query,
        status_filter,
    )


def _project_submissions_page_data(request, course, project):
    search_query, status_filter = _project_submissions_request_filters(
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


@staff_required
def project_submissions(request, course_slug, project_slug):
    """View all submissions for a project"""
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )
    _apply_project_action_flags(project)
    context_data = _project_submissions_page_data(
        request,
        course,
        project,
    )
    context = _project_submissions_context(context_data)
    return render(request, "cadmin/project_submissions.html", context)


def _project_submission_edit_objects(
    course_slug,
    project_slug,
    submission_id,
):
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )
    submission = get_object_or_404(
        ProjectSubmission, id=submission_id, project=project
    )
    return ProjectSubmissionEditObjects(
        course=course,
        project=project,
        submission=submission,
    )


def _project_review_criteria(course):
    return ReviewCriteria.objects.filter(course=course).order_by("id")


def _project_evaluation_score_map(submission):
    scores = ProjectEvaluationScore.objects.filter(submission=submission)
    score_map = {}
    for score in scores:
        score_map[score.review_criteria_id] = score
    return score_map


def _criteria_with_project_scores(review_criteria, submission):
    evaluation_scores = _project_evaluation_score_map(submission)
    criteria_scores = []
    for criteria in review_criteria:
        evaluation_score = evaluation_scores.get(criteria.id)
        score = 0
        score_id = None
        if evaluation_score is not None:
            score = evaluation_score.score
            score_id = evaluation_score.id
        record = {
            "criteria": criteria,
            "score": score,
            "score_id": score_id,
        }
        criteria_scores.append(record)
    return criteria_scores


def _handle_project_submission_edit_post(data):
    form = ProjectSubmissionEditForm(
        data.request.POST,
        review_criteria=data.review_criteria,
    )
    if not form.is_valid():
        messages.error(
            data.request,
            f"Error updating submission: {first_form_error(form)}",
        )
        return None

    update_project_submission_from_admin(
        data.submission,
        form.cleaned_data,
    )
    messages.success(
        data.request,
        f"Project submission for {data.submission.student.username} updated successfully",
    )
    return redirect(
        "cadmin_project_submissions",
        course_slug=data.course.slug,
        project_slug=data.project.slug,
    )


def _project_submission_edit_context(data):
    return {
        "course": data.course,
        "project": data.project,
        "submission": data.submission,
        "criteria_with_scores": data.criteria_with_scores,
    }


def _project_submission_edit_response(data):
    context = _project_submission_edit_context(data)
    return render(
        data.request, "cadmin/project_submission_edit.html", context
    )


def _project_submission_edit_page_data(request, edit_objects):
    review_criteria = _project_review_criteria(edit_objects.course)
    criteria_with_scores = _criteria_with_project_scores(
        review_criteria,
        edit_objects.submission,
    )
    return ProjectSubmissionEditPageData(
        request=request,
        course=edit_objects.course,
        project=edit_objects.project,
        submission=edit_objects.submission,
        review_criteria=review_criteria,
        criteria_with_scores=criteria_with_scores,
    )


@staff_required
def project_submission_edit(
    request, course_slug, project_slug, submission_id
):
    """Edit a project submission"""
    edit_objects = _project_submission_edit_objects(
        course_slug,
        project_slug,
        submission_id,
    )
    edit_data = _project_submission_edit_page_data(request, edit_objects)

    if request.method == "POST":
        response = _handle_project_submission_edit_post(edit_data)
        if response is not None:
            return response

    return _project_submission_edit_response(edit_data)
