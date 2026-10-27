from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt

from accounts.auth import token_required
from courses.models.course import Course
from courses.models.homework import Homework
from courses.models.homework import HomeworkState
from courses.scoring import (
    HomeworkScoringStatus,
)
from courses.scoring_queue import (
    enqueue_homework_scoring,
    homework_score_precheck,
    job_poll_path_homework,
    job_to_dict,
    latest_homework_job,
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


def _homework_score_blocked_response(homework, message):
    homework.refresh_from_db()
    payload = {
        "status": HomeworkScoringStatus.FAIL.name,
        "message": message,
        "homework_id": homework.id,
        "homework_slug": homework.slug,
        "state": homework.state,
        "submissions_count": homework.submission_set.count(),
        "rescored_submissions_count": 0,
    }
    return JsonResponse(payload, status=400)


def _homework_score_enqueued_response(request, homework, force=False):
    requested_by = getattr(request.user, "username", "") or ""
    job, created = enqueue_homework_scoring(
        homework, requested_by=requested_by, force=force
    )
    homework.refresh_from_db()
    if created:
        message = (
            f"Scoring queued for homework {homework.id} "
            f"(job #{job.id}). Poll for status."
        )
    else:
        message = (
            f"Scoring already in progress for homework {homework.id} "
            f"(job #{job.id})."
        )
    by_slug = "by_slug" in request.path
    poll_url = job_poll_path_homework(
        homework.course.slug,
        homework_slug=homework.slug if by_slug else None,
        homework_id=None if by_slug else homework.id,
    )
    payload = {
        "status": job.status.upper(),
        "message": message,
        "homework_id": homework.id,
        "homework_slug": homework.slug,
        "state": homework.state,
        "submissions_count": homework.submission_set.count(),
        "rescored_submissions_count": 0,
        "job_id": job.id,
        "job_status": job.status,
        "poll_url": poll_url,
    }
    payload.update(job_to_dict(job))
    payload["job_id"] = job.id
    payload["job_status"] = job.status
    return JsonResponse(payload, status=202)


def _homework_score_status_response(homework):
    job = latest_homework_job(homework)
    if job is None:
        return JsonResponse({"error": "No scoring job for this homework"}, status=404)
    homework.refresh_from_db()
    payload = {
        "homework_id": homework.id,
        "homework_slug": homework.slug,
        "state": homework.state,
        "submissions_count": homework.submission_set.count(),
    }
    payload.update(job_to_dict(job))
    payload["status"] = job.status.upper()
    payload["message"] = job.result_message or job.last_error
    if job.status == "succeeded":
        payload["rescored_submissions_count"] = payload["submissions_count"]
    else:
        payload["rescored_submissions_count"] = 0
    return JsonResponse(payload)


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
@require_methods("GET", "POST")
def homework_score_view(request, course_slug, homework_id):
    """
    POST /api/courses/<slug>/homeworks/<id>/score/ - Queue homework scoring.
    GET /api/courses/<slug>/homeworks/<id>/score/ - Scoring job status.
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
    if request.method == "GET":
        return _homework_score_status_response(homework)
    error = homework_score_precheck(homework)
    if error:
        return _homework_score_blocked_response(homework, error)
    return _homework_score_enqueued_response(request, homework)


@token_required
@csrf_exempt
@require_methods("GET", "POST")
def homework_score_by_slug_view(request, course_slug, homework_slug):
    """
    POST /api/courses/<slug>/homeworks/by-slug/<slug>/score/ - Queue scoring.
    GET /api/courses/<slug>/homeworks/by-slug/<slug>/score/ - Job status.
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
    if request.method == "GET":
        return _homework_score_status_response(homework)
    error = homework_score_precheck(homework)
    if error:
        return _homework_score_blocked_response(homework, error)
    return _homework_score_enqueued_response(request, homework)
