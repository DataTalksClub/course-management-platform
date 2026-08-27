import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.auth import token_required
from course_management.datamailer.sync.certificates import (
    send_certificate_availability_notification,
)
from courses.models.course import Course, Enrollment, User

from .enrollment_certificate_updates import process_certificate_updates


@csrf_exempt
@require_POST
@token_required
def bulk_update_enrollment_certificates_view(request, course_slug: str):
    certificate_updates, error_response = _certificate_request_updates(request)
    if error_response:
        return error_response

    course = get_object_or_404(Course, slug=course_slug)
    updated, errors = process_certificate_updates(
        course,
        course_slug,
        certificate_updates,
    )

    return _certificate_update_response(updated, errors)


@csrf_exempt
@require_POST
@token_required
def notify_enrollment_certificate_view(request, course_slug: str):
    email, error_response = _certificate_notify_email(request)
    if error_response:
        return error_response

    course = get_object_or_404(Course, slug=course_slug)
    enrollment, error = _enrollment_for_certificate_notification(
        course, course_slug, email
    )
    if error:
        return JsonResponse({"success": False, **error})

    send_certificate_availability_notification(enrollment)

    payload = {
        "success": True,
        "email": email,
        "enrollment_id": enrollment.id,
        "certificate_url": enrollment.certificate_url,
    }
    return JsonResponse(payload)


def _certificate_notify_email(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        error_payload = {"error": "Invalid JSON"}
        error_response = JsonResponse(error_payload, status=400)
        return None, error_response

    email = data.get("email") if isinstance(data, dict) else None
    if not email:
        error_payload = {"error": "email is required"}
        error_response = JsonResponse(error_payload, status=400)
        return None, error_response

    return email, None


def _enrollment_for_certificate_notification(course, course_slug, email):
    if not User.objects.filter(email__iexact=email).exists():
        error = {
            "email": email,
            "code": "user_not_found",
            "error": f"User with email {email} not found",
        }
        return None, error

    enrollment = (
        Enrollment.objects.filter(course=course, student__email__iexact=email)
        .select_related("student")
        .first()
    )
    if enrollment is None:
        error = {
            "email": email,
            "code": "not_enrolled",
            "error": f"User {email} is not enrolled in course {course_slug}",
        }
        return None, error

    if not enrollment.certificate_url:
        error = {
            "email": email,
            "code": "certificate_missing",
            "error": f"User {email} does not have a certificate yet",
        }
        return None, error

    return enrollment, None


def _certificate_request_updates(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        error_payload = {"error": "Invalid JSON"}
        error_response = JsonResponse(error_payload, status=400)
        return None, error_response

    certificate_updates = _extract_certificate_updates(data)
    if not isinstance(certificate_updates, list):
        error_payload = {"error": "Expected a certificates array"}
        error_response = JsonResponse(error_payload, status=400)
        return None, error_response

    if not certificate_updates:
        error_payload = {
            "error": "At least one certificate update is required"
        }
        error_response = JsonResponse(error_payload, status=400)
        return None, error_response

    return certificate_updates, None


def _extract_certificate_updates(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("certificates")
    return None


def _certificate_update_response(updated, errors):
    success = len(errors) == 0
    updated_count = len(updated)
    error_count = len(errors)
    payload = {
        "success": success,
        "updated_count": updated_count,
        "error_count": error_count,
        "updated": updated,
        "errors": errors,
    }
    response = JsonResponse(payload)
    return response
