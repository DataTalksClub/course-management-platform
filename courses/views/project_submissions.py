from dataclasses import dataclass

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from courses.models import (
    Course,
    PeerReview,
    Project,
    ProjectState,
    ProjectSubmission,
)
from courses.votes import (
    PROJECT_VOTES_PER_PROJECT,
    get_project_vote_counts,
    get_voted_submission_ids,
    update_project_vote,
)


PROJECT_SUBMISSIONS_PAGE_SIZE = 25


@dataclass(frozen=True)
class ProjectSubmissionsDecorationData:
    submissions_list: list
    project: Project
    is_authenticated: bool
    review_ids: dict
    own_submissions: set
    voted_submission_ids: set
    project_vote_counts: dict
    has_assigned_reviews: bool


@dataclass(frozen=True)
class SubmissionViewerStateData:
    submission: ProjectSubmission
    project: Project
    own_submissions: set
    voted_submission_ids: set
    project_vote_counts: dict


@dataclass(frozen=True)
class SubmissionReviewGroupData:
    submission: ProjectSubmission
    in_peer_review: bool
    has_assigned_reviews: bool


def paginate_project_submissions(request, submissions):
    paginator = Paginator(submissions, PROJECT_SUBMISSIONS_PAGE_SIZE)
    return paginator.get_page(request.GET.get("page"))


def _project_vote_response(request, course, project):
    """Handle a POST vote on a project submission (HTML redirect or AJAX JSON)."""
    if not request.user.is_authenticated:
        return redirect("login")

    submission = _project_vote_submission(request, project)
    update_project_vote(
        request.user,
        submission,
        action=request.POST.get("action", "vote"),
    )

    if _is_ajax_request(request):
        return JsonResponse(
            _project_vote_payload(request.user, course, project, submission)
        )

    return redirect(
        "project_list",
        course_slug=course.slug,
        project_slug=project.slug,
    )


def _is_ajax_request(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def _project_vote_submission(request, project):
    return get_object_or_404(
        ProjectSubmission.objects.select_related("project"),
        id=request.POST.get("submission_id"),
        project=project,
        volunteer_review_only=False,
    )


def _project_submission_vote_count(submission):
    return (
        ProjectSubmission.objects.filter(id=submission.id)
        .annotate(vote_count=Count("votes"))
        .values_list("vote_count", flat=True)
        .get()
    )


def _project_vote_payload(user, course, project, submission):
    voted_submission_ids = get_voted_submission_ids(user, course)
    project_vote_counts = get_project_vote_counts(user, course)
    project_vote_count = project_vote_counts.get(project.id, 0)
    votes_left = max(PROJECT_VOTES_PER_PROJECT - project_vote_count, 0)

    return {
        "submission_id": submission.id,
        "vote_count": _project_submission_vote_count(submission),
        "voted": submission.id in voted_submission_ids,
        "voted_submission_ids": list(voted_submission_ids),
        "votes_left": votes_left,
        "vote_limit_reached": (
            project_vote_count >= PROJECT_VOTES_PER_PROJECT
        ),
    }


def _decorate_project_submissions(data):
    """Attach per-submission display flags (ordering, ownership, review group)."""
    in_peer_review = (
        data.is_authenticated
        and data.project.state == ProjectState.PEER_REVIEWING.value
    )

    for order, submission in enumerate(data.submissions_list):
        submission.list_order = order
        _decorate_submission_review_state(submission, data.review_ids)
        viewer_data = SubmissionViewerStateData(
            submission=submission,
            project=data.project,
            own_submissions=data.own_submissions,
            voted_submission_ids=data.voted_submission_ids,
            project_vote_counts=data.project_vote_counts,
        )
        _decorate_submission_viewer_state(viewer_data)
        review_group_data = SubmissionReviewGroupData(
            submission,
            in_peer_review=in_peer_review,
            has_assigned_reviews=data.has_assigned_reviews,
        )
        _decorate_submission_review_group(review_group_data)


def _decorate_submission_review_state(submission, review_ids):
    if submission.id in review_ids:
        submission.to_evaluate = True
        submission.review = review_ids[submission.id]
        return

    submission.to_evaluate = False


def _decorate_submission_viewer_state(data):
    data.submission.own = data.submission.id in data.own_submissions
    data.submission.vote_limit_reached = (
        data.submission.id not in data.voted_submission_ids
        and data.project_vote_counts.get(data.project.id, 0)
        >= PROJECT_VOTES_PER_PROJECT
    )


def _decorate_submission_review_group(data):
    submission = data.submission
    submission.group_order = 1
    submission.group_label = None

    if not data.in_peer_review:
        return

    if submission.to_evaluate and not submission.review.optional:
        submission.group_order = 0
        submission.group_label = "Assigned reviews"
        return

    if data.has_assigned_reviews:
        submission.group_label = "Other submissions"


def _project_submissions_queryset(project):
    submissions = (
        ProjectSubmission.objects.filter(
            project=project,
            volunteer_review_only=False,
        )
        .select_related("enrollment")
        .annotate(vote_count=Count("votes"))
    )

    if project.state == ProjectState.COMPLETED.value:
        return submissions.order_by("-project_score")

    return submissions.order_by("-submitted_at")


def _project_viewer_state(project, course, user):
    state = _base_project_viewer_state(
        _project_viewer_vote_state(project, course, user)
    )

    if not user.is_authenticated:
        return state

    state["is_authenticated"] = True
    student_submissions, own_submissions = (
        _project_viewer_student_submissions(project, user)
    )
    review_ids, has_assigned_reviews = _project_viewer_reviews(
        project,
        student_submissions,
    )

    state.update(
        {
            "review_ids": review_ids,
            "own_submissions": own_submissions,
            "has_submission": len(own_submissions) > 0,
            "has_assigned_reviews": has_assigned_reviews,
        }
    )
    return state


def _project_viewer_vote_state(project, course, user):
    voted_submission_ids = get_voted_submission_ids(user, course)
    project_vote_counts = get_project_vote_counts(user, course)
    project_vote_count = project_vote_counts.get(project.id, 0)
    return {
        "voted_submission_ids": voted_submission_ids,
        "project_vote_counts": project_vote_counts,
        "project_votes_left": max(
            PROJECT_VOTES_PER_PROJECT - project_vote_count,
            0,
        ),
    }


def _base_project_viewer_state(vote_state):
    return {
        "is_authenticated": False,
        "review_ids": {},
        "own_submissions": set(),
        "has_submission": False,
        **vote_state,
        "has_assigned_reviews": False,
    }


def _project_viewer_student_submissions(project, user):
    student_submissions = ProjectSubmission.objects.filter(
        project=project, student=user
    )
    project_submissions = student_submissions.filter(
        volunteer_review_only=False,
    )
    own_submissions = set(project_submissions.values_list("id", flat=True))
    return student_submissions, own_submissions


def _project_viewer_reviews(project, student_submissions):
    review_ids = {}
    has_assigned_reviews = False
    reviews = PeerReview.objects.filter(
        reviewer__in=student_submissions,
        submission_under_evaluation__project=project,
    )
    for review in reviews:
        eval_id = review.submission_under_evaluation_id
        review_ids[eval_id] = review
        if not review.optional:
            has_assigned_reviews = True

    return review_ids, has_assigned_reviews


def _sort_project_submissions_for_view(
    submissions_list,
    *,
    project,
    viewer_state,
):
    if _project_submissions_use_review_group_sort(project, viewer_state):
        submissions_list.sort(
            key=lambda submission: (
                submission.group_order,
                submission.list_order,
            )
        )


def _project_submissions_use_review_group_sort(project, viewer_state):
    return (
        viewer_state["is_authenticated"]
        and project.state == ProjectState.PEER_REVIEWING.value
    )


def _apply_project_group_headings(submissions_page):
    previous_group_label = None
    submissions = submissions_page.object_list
    for submission in submissions:
        submission.group_heading = None
        if (
            submission.group_label
            and submission.group_label != previous_group_label
        ):
            submission.group_heading = submission.group_label
        previous_group_label = submission.group_label


def projects_list_view(request, course_slug, project_slug):
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )

    if request.method == "POST":
        return _project_vote_response(request, course, project)

    user = request.user
    viewer_state = _project_viewer_state(project, course, user)
    submissions_page = _project_submissions_page(
        request, project, viewer_state
    )
    context = _projects_list_context(
        course, project, submissions_page, viewer_state
    )

    return render(request, "projects/list.html", context)


def _project_submissions_page(request, project, viewer_state):
    submissions_list = list(_project_submissions_queryset(project))
    decoration_data = ProjectSubmissionsDecorationData(
        submissions_list=submissions_list,
        project=project,
        is_authenticated=viewer_state["is_authenticated"],
        review_ids=viewer_state["review_ids"],
        own_submissions=viewer_state["own_submissions"],
        voted_submission_ids=viewer_state["voted_submission_ids"],
        project_vote_counts=viewer_state["project_vote_counts"],
        has_assigned_reviews=viewer_state["has_assigned_reviews"],
    )
    _decorate_project_submissions(decoration_data)
    _sort_project_submissions_for_view(
        submissions_list,
        project=project,
        viewer_state=viewer_state,
    )

    submissions_page = paginate_project_submissions(
        request, submissions_list
    )
    _apply_project_group_headings(submissions_page)
    return submissions_page


def _projects_list_context(course, project, submissions_page, viewer_state):
    return {
        "course": course,
        "project": project,
        "submissions": submissions_page.object_list,
        "submissions_page": submissions_page,
        "page_range": submissions_page.paginator.get_elided_page_range(
            submissions_page.number
        ),
        "is_authenticated": viewer_state["is_authenticated"],
        "has_submission": viewer_state["has_submission"],
        "voted_submission_ids": viewer_state["voted_submission_ids"],
        "project_votes_per_project": PROJECT_VOTES_PER_PROJECT,
        "project_votes_left": viewer_state["project_votes_left"],
    }


def project_submissions(request, course_slug, project_slug):
    if not request.user.is_authenticated or not request.user.is_staff:
        messages.error(
            request,
            "You do not have permission to view this page.",
            extra_tags="project",
        )
        return redirect(
            "project",
            course_slug=course_slug,
            project_slug=project_slug,
        )

    return redirect(
        "cadmin_project_submissions",
        course_slug=course_slug,
        project_slug=project_slug,
    )
