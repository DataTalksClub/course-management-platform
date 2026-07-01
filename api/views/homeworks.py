from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt

from accounts.auth import token_required
from courses.models import Course, Homework
from courses.models.homework import HomeworkState
from courses.scoring import (
    HomeworkScoringStatus,
    score_homework_submissions,
)

from api.crud import (
    DeleteResponseConfig,
    DetailResponseConfig,
    detail_response,
    get_course_child_or_404,
)
from api.safety import (
    require_staff_token,
)
from api.utils import (
    require_methods,
)
from api.views.homework_create import (
    homeworks_create_response,
    homeworks_list_response,
)
from api.views.homework_upsert import (
    HOMEWORK_PATCH_CONFIG,
    staff_upsert_homework_by_slug,
)


def _homework_score_response(homework):
    status, message = score_homework_submissions(homework.id)
    homework.refresh_from_db()
    submissions_count = homework.submission_set.count()
    if status == HomeworkScoringStatus.OK:
        response_status = 200
    else:
        response_status = 400

    if status == HomeworkScoringStatus.OK:
        rescored_submissions_count = submissions_count
    else:
        rescored_submissions_count = 0

    payload = {
        "status": status.name,
        "message": message,
        "homework_id": homework.id,
        "homework_slug": homework.slug,
        "state": homework.state,
        "submissions_count": submissions_count,
        "rescored_submissions_count": rescored_submissions_count,
    }
    response = JsonResponse(payload, status=response_status)
    return response


@token_required
@csrf_exempt
@require_methods("GET", "POST")
def homeworks_view(request, course_slug):
    """
    GET /api/courses/<slug>/homeworks/ - List homeworks.
    POST /api/courses/<slug>/homeworks/ - Create homework(s), bulk supported.
    """
    course = get_object_or_404(Course, slug=course_slug)

    if request.method == "GET":
        return homeworks_list_response(course)

    return homeworks_create_response(request, course)


def _homework_detail_config(homework):
    related_queryset = homework.submission_set.all()
    delete_config = DeleteResponseConfig(
        closed_state=HomeworkState.CLOSED.value,
        related_queryset=related_queryset,
        related_name="submissions",
        noun="homework",
    )
    config = DetailResponseConfig(
        patch=HOMEWORK_PATCH_CONFIG,
        delete=delete_config,
    )
    return config


def _homework_detail_response(
    request,
    course_slug,
    *,
    homework_id=None,
    homework_slug=None,
):
    course = get_object_or_404(Course, slug=course_slug)
    homework = get_course_child_or_404(
        Homework,
        course,
        object_id=homework_id,
        slug=homework_slug,
    )
    config = _homework_detail_config(homework)
    return detail_response(
        request,
        homework,
        config,
    )


@token_required
@csrf_exempt
@require_methods("GET", "PATCH", "DELETE")
def homework_detail_view(request, course_slug, homework_id):
    """
    GET /api/courses/<slug>/homeworks/<id>/ - Homework detail.
    PATCH /api/courses/<slug>/homeworks/<id>/ - Update homework.
    DELETE /api/courses/<slug>/homeworks/<id>/ - Delete homework.
    """
    return _homework_detail_response(
        request, course_slug, homework_id=homework_id
    )


@token_required
@csrf_exempt
@require_methods("GET", "PUT", "PATCH", "DELETE")
def homework_detail_by_slug_view(request, course_slug, homework_slug):
    """
    GET /api/courses/<slug>/homeworks/by-slug/<slug>/ - Homework detail.
    PUT /api/courses/<slug>/homeworks/by-slug/<slug>/ - Upsert homework.
    PATCH /api/courses/<slug>/homeworks/by-slug/<slug>/ - Update homework.
    DELETE /api/courses/<slug>/homeworks/by-slug/<slug>/ - Delete homework.
    """
    if request.method == "PUT":
        return staff_upsert_homework_by_slug(
            request, course_slug, homework_slug
        )

    return _homework_detail_response(
        request, course_slug, homework_slug=homework_slug
    )


@token_required
@csrf_exempt
@require_methods("POST")
def homework_score_view(request, course_slug, homework_id):
    """
    POST /api/courses/<slug>/homeworks/<id>/score/ - Score homework.
    """
    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    course = get_object_or_404(Course, slug=course_slug)
    homework = get_course_child_or_404(
        Homework,
        course,
        object_id=homework_id,
    )
    return _homework_score_response(homework)


@token_required
@csrf_exempt
@require_methods("POST")
def homework_score_by_slug_view(request, course_slug, homework_slug):
    """
    POST /api/courses/<slug>/homeworks/by-slug/<slug>/score/ - Score homework.
    """
    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    course = get_object_or_404(Course, slug=course_slug)
    homework = get_course_child_or_404(
        Homework,
        course,
        slug=homework_slug,
    )
    return _homework_score_response(homework)
