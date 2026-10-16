from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt

from accounts.auth import token_required
from courses.models.course import Course
from courses.models.project import ReviewCriteria

from api.safety import (
    require_staff_token,
)
from api.utils import parse_json_body, require_methods

from .review_criteria_mutations import (
    review_criteria_create_response,
    review_criteria_delete_response,
    review_criteria_patch_response,
)
from .review_criteria_serializers import review_criteria_to_dict


def _get_course(course_slug):
    return get_object_or_404(Course, slug=course_slug)


def _review_criteria_list_response(course):
    criteria_records = (
        ReviewCriteria.objects.filter(course=course)
        .annotate(scores_count=Count("projectevaluationscore"))
        .order_by("id")
    )
    criteria_list = []
    for criteria in criteria_records:
        criteria_record = review_criteria_to_dict(criteria)
        criteria_list.append(criteria_record)

    payload = {
        "course_slug": course.slug,
        "course_title": course.title,
        "review_criteria": criteria_list,
    }
    response = JsonResponse(payload)
    return response


@token_required
@csrf_exempt
@require_methods("GET", "POST")
def review_criteria_view(request, course_slug):
    """
    GET /api/courses/<slug>/review-criteria/ - List review criteria.
    POST /api/courses/<slug>/review-criteria/ - Add review criteria.
    """
    course = _get_course(course_slug)

    if request.method == "GET":
        return _review_criteria_list_response(course)

    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    data, err = parse_json_body(request)
    if err:
        return err

    return review_criteria_create_response(course, data)


@token_required
@csrf_exempt
@require_methods("GET", "PATCH", "DELETE")
def review_criteria_detail_view(request, course_slug, criteria_id):
    """
    GET /api/courses/<slug>/review-criteria/<id>/ - Review criteria detail.
    PATCH /api/courses/<slug>/review-criteria/<id>/ - Update review criteria.
    DELETE /api/courses/<slug>/review-criteria/<id>/ - Delete review criteria.
    """
    course = _get_course(course_slug)
    criteria = get_object_or_404(
        ReviewCriteria, course=course, id=criteria_id
    )

    if request.method == "GET":
        criteria_record = review_criteria_to_dict(criteria)
        response = JsonResponse(criteria_record)
        return response

    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    if request.method == "DELETE":
        return review_criteria_delete_response(criteria)

    return review_criteria_patch_response(criteria, request)
