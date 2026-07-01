from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt

from accounts.auth import token_required
from api.safety import require_staff_token
from api.utils import require_methods
from api.views.course_mutations import (
    apply_course_patch_data,
    course_create_data_from_request,
    course_patch_data_from_request,
    course_validation_error,
    validated_course_from_create_data,
)
from api.views.course_serializers import (
    course_detail_to_dict,
    course_summary_to_dict,
    course_to_dict,
)
from courses.models import Course


def courses_list_response():
    courses = Course.objects.all().order_by("id")
    course_records = []
    for course in courses:
        course_record = course_summary_to_dict(course)
        course_records.append(course_record)

    payload = {
        "courses": course_records,
    }
    response = JsonResponse(payload)
    return response


def create_course_response(request):
    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    data, err = course_create_data_from_request(request)
    if err:
        return err

    course, err = validated_course_from_create_data(data)
    if err:
        return err

    course.save()
    course_data = course_to_dict(course)
    response = JsonResponse(course_data, status=201)
    return response


@token_required
@csrf_exempt
@require_methods("GET", "POST")
def courses_list_view(request):
    if request.method == "GET":
        return courses_list_response()

    return create_course_response(request)


def patch_course_response(request, course):
    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    data, err = course_patch_data_from_request(request)
    if err:
        return err

    apply_course_patch_data(course, data)
    err = course_validation_error(course)
    if err:
        return err

    course.save()
    course_data = course_to_dict(course)
    response = JsonResponse(course_data)
    return response


@token_required
@csrf_exempt
@require_methods("GET", "PATCH")
def course_detail_view(request, course_slug):
    course = get_object_or_404(Course, slug=course_slug)

    if request.method == "PATCH":
        return patch_course_response(request, course)

    course_data = course_detail_to_dict(course)
    response = JsonResponse(course_data)
    return response
