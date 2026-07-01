from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt

from accounts.auth import token_required
from courses.models import Course, Project, PeerReview
from courses.models.project import ProjectState
from courses.project_assignment import (
    ProjectActionStatus,
    assign_peer_reviews_for_project,
)
from courses.projects import (
    score_project,
)

from api.crud import (
    DeleteResponseConfig,
    DetailResponseConfig,
    PatchResponseConfig,
    detail_response,
    get_course_child_or_404,
)
from api.safety import (
    require_staff_token,
)
from api.utils import (
    require_methods,
)
from api.views.project_create import (
    projects_create_response,
    projects_list_response,
)
from api.views.project_serializers import project_to_dict
from api.views.project_upsert import (
    PROJECT_PATCH_RULES,
    staff_upsert_project_by_slug,
)


def _project_action_base(project, status, message):
    project.refresh_from_db()
    return {
        "status": status.name,
        "message": message,
        "project_id": project.id,
        "project_slug": project.slug,
        "state": project.state,
    }


def _project_assign_reviews_response(project):
    before_count = PeerReview.objects.filter(
        submission_under_evaluation__project=project,
    ).count()
    status, message = assign_peer_reviews_for_project(project)
    after_count = PeerReview.objects.filter(
        submission_under_evaluation__project=project,
    ).count()
    if status == ProjectActionStatus.OK:
        assigned_peer_reviews_count = after_count - before_count
        response_status = 200
    else:
        assigned_peer_reviews_count = 0
        response_status = 400
    data = _project_action_base(project, status, message)
    data.update(
        {
            "peer_reviews_count": after_count,
            "assigned_peer_reviews_count": assigned_peer_reviews_count,
        }
    )
    response = JsonResponse(
        data,
        status=response_status,
    )
    return response


def _project_scorable_submissions_count(project):
    return (
        PeerReview.objects.filter(
            submission_under_evaluation__project=project,
        )
        .values("submission_under_evaluation")
        .distinct()
        .count()
    )


def _project_score_response(project):
    scorable_submissions_count = _project_scorable_submissions_count(project)
    status, message = score_project(project)
    submissions = project.projectsubmission_set.all()
    response_status = 400
    scored_count = 0
    passed_count = 0
    if status == ProjectActionStatus.OK:
        response_status = 200
        scored_count = scorable_submissions_count
        passed_count = submissions.filter(passed=True).count()

    data = _project_action_base(project, status, message)
    data.update(
        {
            "submissions_count": submissions.count(),
            "scored_submissions_count": scored_count,
            "passed_submissions_count": passed_count,
        }
    )
    response = JsonResponse(
        data,
        status=response_status,
    )
    return response


@token_required
@csrf_exempt
@require_methods("GET", "POST")
def projects_view(request, course_slug):
    """
    GET /api/courses/<slug>/projects/ - List projects.
    POST /api/courses/<slug>/projects/ - Create project(s), bulk supported.
    """
    course = get_object_or_404(Course, slug=course_slug)

    if request.method == "GET":
        return projects_list_response(course)

    return projects_create_response(request, course)


def _project_detail_config(project):
    return DetailResponseConfig(
        patch=PatchResponseConfig(
            to_dict=project_to_dict,
            rules=PROJECT_PATCH_RULES,
        ),
        delete=DeleteResponseConfig(
            closed_state=ProjectState.CLOSED.value,
            related_queryset=project.projectsubmission_set.all(),
            related_name="submissions",
            noun="project",
        ),
    )


def _project_detail_response(
    request,
    course_slug,
    *,
    project_id=None,
    project_slug=None,
):
    course = get_object_or_404(Course, slug=course_slug)
    project = get_course_child_or_404(
        Project,
        course,
        object_id=project_id,
        slug=project_slug,
    )
    config = _project_detail_config(project)
    return detail_response(
        request,
        project,
        config,
    )


@token_required
@csrf_exempt
@require_methods("GET", "PATCH", "DELETE")
def project_detail_view(request, course_slug, project_id):
    """
    GET /api/courses/<slug>/projects/<id>/ - Project detail.
    PATCH /api/courses/<slug>/projects/<id>/ - Update project.
    DELETE /api/courses/<slug>/projects/<id>/ - Delete project.
    """
    return _project_detail_response(
        request, course_slug, project_id=project_id
    )


@token_required
@csrf_exempt
@require_methods("GET", "PUT", "PATCH", "DELETE")
def project_detail_by_slug_view(request, course_slug, project_slug):
    """
    GET /api/courses/<slug>/projects/by-slug/<slug>/ - Project detail.
    PUT /api/courses/<slug>/projects/by-slug/<slug>/ - Upsert project.
    PATCH /api/courses/<slug>/projects/by-slug/<slug>/ - Update project.
    DELETE /api/courses/<slug>/projects/by-slug/<slug>/ - Delete project.
    """
    if request.method == "PUT":
        return staff_upsert_project_by_slug(
            request, course_slug, project_slug
        )

    return _project_detail_response(
        request, course_slug, project_slug=project_slug
    )


@token_required
@csrf_exempt
@require_methods("POST")
def project_assign_reviews_view(request, course_slug, project_id):
    """
    POST /api/courses/<slug>/projects/<id>/assign-reviews/ - Assign reviews.
    """
    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    course = get_object_or_404(Course, slug=course_slug)
    project = get_course_child_or_404(
        Project,
        course,
        object_id=project_id,
    )
    return _project_assign_reviews_response(project)


@token_required
@csrf_exempt
@require_methods("POST")
def project_assign_reviews_by_slug_view(
    request, course_slug, project_slug
):
    """
    POST /api/courses/<slug>/projects/by-slug/<slug>/assign-reviews/ - Assign reviews.
    """
    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    course = get_object_or_404(Course, slug=course_slug)
    project = get_course_child_or_404(
        Project,
        course,
        slug=project_slug,
    )
    return _project_assign_reviews_response(project)


@token_required
@csrf_exempt
@require_methods("POST")
def project_score_view(request, course_slug, project_id):
    """
    POST /api/courses/<slug>/projects/<id>/score/ - Score project.
    """
    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    course = get_object_or_404(Course, slug=course_slug)
    project = get_course_child_or_404(
        Project,
        course,
        object_id=project_id,
    )
    return _project_score_response(project)


@token_required
@csrf_exempt
@require_methods("POST")
def project_score_by_slug_view(request, course_slug, project_slug):
    """
    POST /api/courses/<slug>/projects/by-slug/<slug>/score/ - Score project.
    """
    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    course = get_object_or_404(Course, slug=course_slug)
    project = get_course_child_or_404(
        Project,
        course,
        slug=project_slug,
    )
    return _project_score_response(project)
