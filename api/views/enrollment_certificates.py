import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from accounts.auth import token_required
from course_management.datamailer.sync import (
    send_certificate_availability_notification,
)
from courses.models import Course

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
        send_certificate_availability_notification,
    )

    return _certificate_update_response(updated, errors)


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
