from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt

from accounts.auth import token_required
from courses.models.course import Course
from courses.models.project import Project
from courses.models.project import ProjectState

from api.crud import (
    DeleteResponseConfig,
    DetailResponseConfig,
    PatchResponseConfig,
    detail_response,
    get_course_child_or_404,
)
from api.utils import (
    require_methods,
)
from api.views.project_action_routes import (
    ProjectActionRouteData,
    project_action_route_response,
)
from api.views.project_actions import (
    project_assign_reviews_response,
    project_score_response,
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
    patch_config = PatchResponseConfig(
        to_dict=project_to_dict,
        rules=PROJECT_PATCH_RULES,
    )
    related_queryset = project.projectsubmission_set.all()
    delete_config = DeleteResponseConfig(
        closed_state=ProjectState.CLOSED.value,
        related_queryset=related_queryset,
        related_name="submissions",
        noun="project",
    )
    config = DetailResponseConfig(
        patch=patch_config,
        delete=delete_config,
    )
    return config


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
    route_data = ProjectActionRouteData(
        request=request,
        course_slug=course_slug,
        project_id=project_id,
    )
    response = project_action_route_response(
        route_data,
        project_assign_reviews_response,
    )
    return response


@token_required
@csrf_exempt
@require_methods("POST")
def project_assign_reviews_by_slug_view(
    request, course_slug, project_slug
):
    """
    POST /api/courses/<slug>/projects/by-slug/<slug>/assign-reviews/ - Assign reviews.
    """
    route_data = ProjectActionRouteData(
        request=request,
        course_slug=course_slug,
        project_slug=project_slug,
    )
    response = project_action_route_response(
        route_data,
        project_assign_reviews_response,
    )
    return response


@token_required
@csrf_exempt
@require_methods("POST")
def project_score_view(request, course_slug, project_id):
    """
    POST /api/courses/<slug>/projects/<id>/score/ - Score project.
    """
    route_data = ProjectActionRouteData(
        request=request,
        course_slug=course_slug,
        project_id=project_id,
    )
    response = project_action_route_response(
        route_data,
        project_score_response,
    )
    return response


@token_required
@csrf_exempt
@require_methods("POST")
def project_score_by_slug_view(request, course_slug, project_slug):
    """
    POST /api/courses/<slug>/projects/by-slug/<slug>/score/ - Score project.
    """
    route_data = ProjectActionRouteData(
        request=request,
        course_slug=course_slug,
        project_slug=project_slug,
    )
    response = project_action_route_response(
        route_data,
        project_score_response,
    )
    return response
