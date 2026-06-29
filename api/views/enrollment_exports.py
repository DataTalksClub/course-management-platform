"""
Enrollment-related data API views.

Provides views for managing enrollment certificates and retrieving graduates data.
"""

import json
from collections import Counter
from dataclasses import dataclass

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from accounts.auth import token_required
from course_management.datamailer import (
    send_certificate_availability_notification,
)

from courses.models import (
    User,
    Enrollment,
    Course,
    ProjectSubmission,
)


@dataclass
class CertificateApplyResult:
    enrollment: Enrollment | None = None
    notify: bool = False
    updated: dict | None = None
    error: dict | None = None


def get_passed_enrollments(passed_project_submissions, min_projects):
    """
    Helper function to get enrollments that passed the minimum required projects.

    Args:
        passed_project_submissions: QuerySet of passed ProjectSubmission objects
        min_projects: Minimum number of projects required to pass

    Returns:
        List of Enrollment objects that passed the minimum required projects
    """
    assert min_projects > 0, "min_projects must be greater than 0"

    counter_passed = Counter()
    ids_mapping = {}

    for s in passed_project_submissions:
        e = s.enrollment
        eid = e.id
        counter_passed[eid] += 1
        ids_mapping[eid] = e

    passed_enrollments = []

    for eid, count in counter_passed.items():
        if count >= min_projects:
            passed_enrollments.append(ids_mapping[eid])

    return passed_enrollments


@require_GET
@token_required
def graduates_data_view(request, course_slug: str):
    """Get list of students who graduated (passed enough projects) from a course."""
    course = get_object_or_404(Course, slug=course_slug)

    passed_project_submissions = ProjectSubmission.objects.filter(
        project__course=course, passed=True
    ).prefetch_related("enrollment")

    passed_enrollments = get_passed_enrollments(
        passed_project_submissions, course.min_projects_to_pass
    )

    graduates = []

    for enrollment in passed_enrollments:
        student = enrollment.student
        email = student.email
        name = student.certificate_name or enrollment.display_name

        graduates.append(
            {
                "email": email,
                "name": name,
            }
        )

    response = {"graduates": graduates}
    return JsonResponse(response)


def _extract_certificate_updates(data):
    """Pull the updates list from a bare array or a {"certificates": [...]} body."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("certificates")
    return None


def _invalid_certificate_update_item_error(index):
    return {
        "index": index,
        "code": "invalid_item",
        "error": "Each certificate update must be an object",
    }


def _missing_certificate_update_fields_error(index, email):
    return {
        "index": index,
        "email": email,
        "code": "missing_fields",
        "error": "Both email and certificate_path are required",
    }


def _validate_certificate_update_item(index, update):
    if not isinstance(update, dict):
        return None, _invalid_certificate_update_item_error(index)

    email = update.get("email")
    certificate_path = update.get("certificate_path")

    if not email or not certificate_path:
        return None, _missing_certificate_update_fields_error(index, email)

    return {
        "index": index,
        "email": email,
        "certificate_path": certificate_path,
    }, None


def _validate_certificate_update_items(certificate_updates):
    """Split raw items into (valid_updates, errors) by shape + required fields."""
    valid_updates = []
    errors = []

    for index, update in enumerate(certificate_updates):
        valid_update, error = _validate_certificate_update_item(index, update)
        if error:
            errors.append(error)
            continue
        valid_updates.append(valid_update)

    return valid_updates, errors


def _certificate_update_error(update, code, error):
    return {
        "index": update["index"],
        "email": update["email"],
        "code": code,
        "error": error,
    }


def _user_not_found_error(update):
    email = update["email"]
    return _certificate_update_error(
        update,
        "user_not_found",
        f"User with email {email} not found",
    )


def _not_enrolled_error(update, course_slug):
    email = update["email"]
    return _certificate_update_error(
        update,
        "not_enrolled",
        f"User {email} is not enrolled in course {course_slug}",
    )


def _certificate_update_result(update, enrollment):
    return {
        "index": update["index"],
        "email": update["email"],
        "enrollment_id": enrollment.id,
        "certificate_url": update["certificate_path"],
    }


def _should_notify_certificate_available(enrollment, certificate_path):
    had_certificate = bool((enrollment.certificate_url or "").strip())
    return not had_certificate and bool(certificate_path.strip())


def _apply_certificate_update(
    update,
    course_slug,
    users_by_email,
    enrollments_by_email,
):
    email = update["email"]
    certificate_path = update["certificate_path"]

    if email not in users_by_email:
        return CertificateApplyResult(error=_user_not_found_error(update))

    enrollment = enrollments_by_email.get(email)
    if enrollment is None:
        return CertificateApplyResult(
            error=_not_enrolled_error(update, course_slug)
        )

    notify = _should_notify_certificate_available(
        enrollment,
        certificate_path,
    )
    enrollment.certificate_url = certificate_path
    return CertificateApplyResult(
        enrollment=enrollment,
        notify=notify,
        updated=_certificate_update_result(update, enrollment),
    )


def _apply_certificate_updates(
    valid_updates, course_slug, users_by_email, enrollments_by_email
):
    """Apply validated updates to enrollments.

    Returns (enrollments_to_update, enrollments_to_notify, updated, errors),
    where _to_notify holds enrollments that gained a certificate they did not
    have before. Mutates the enrollment objects' certificate_url in place.
    """
    enrollments_to_update = {}
    enrollments_to_notify = {}
    updated = []
    errors = []

    for update in valid_updates:
        result = _apply_certificate_update(
            update,
            course_slug,
            users_by_email,
            enrollments_by_email,
        )
        if result.error:
            errors.append(result.error)
            continue

        enrollments_to_update[result.enrollment.id] = result.enrollment
        if result.notify:
            enrollments_to_notify[result.enrollment.id] = result.enrollment
        updated.append(result.updated)

    return enrollments_to_update, enrollments_to_notify, updated, errors


def _certificate_request_updates(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return None, JsonResponse({"error": "Invalid JSON"}, status=400)

    certificate_updates = _extract_certificate_updates(data)
    if not isinstance(certificate_updates, list):
        return None, JsonResponse(
            {"error": "Expected a certificates array"},
            status=400,
        )

    if not certificate_updates:
        return None, JsonResponse(
            {"error": "At least one certificate update is required"},
            status=400,
        )

    return certificate_updates, None


def _certificate_update_lookups(course, valid_updates):
    emails = []
    for update in valid_updates:
        emails.append(update["email"])

    users_by_email = {}
    for user in User.objects.filter(email__in=emails):
        users_by_email[user.email] = user

    enrollments_by_email = {}
    enrollments = Enrollment.objects.filter(
        course=course,
        student__email__in=emails,
    ).select_related("student")
    for enrollment in enrollments:
        enrollments_by_email[enrollment.student.email] = enrollment

    return users_by_email, enrollments_by_email


def _persist_certificate_updates(enrollments_to_update):
    if enrollments_to_update:
        Enrollment.objects.bulk_update(
            enrollments_to_update.values(),
            ["certificate_url"],
        )


def _queue_certificate_notifications(enrollments_to_notify):
    for enrollment in enrollments_to_notify.values():

        def send_notification(enrollment=enrollment):
            send_certificate_availability_notification(enrollment)

        transaction.on_commit(send_notification)


def _certificate_update_response(updated, errors):
    return JsonResponse(
        {
            "success": len(errors) == 0,
            "updated_count": len(updated),
            "error_count": len(errors),
            "updated": updated,
            "errors": errors,
        }
    )


def _process_certificate_updates(course, course_slug, certificate_updates):
    valid_updates, errors = _validate_certificate_update_items(
        certificate_updates
    )

    users_by_email, enrollments_by_email = _certificate_update_lookups(
        course,
        valid_updates,
    )
    enrollments_to_update, enrollments_to_notify, updated, apply_errors = (
        _apply_certificate_updates(
            valid_updates,
            course_slug,
            users_by_email,
            enrollments_by_email,
        )
    )
    errors.extend(apply_errors)

    _persist_certificate_updates(enrollments_to_update)
    _queue_certificate_notifications(enrollments_to_notify)

    return updated, errors


@csrf_exempt
@require_POST
@token_required
def bulk_update_enrollment_certificates_view(request, course_slug: str):
    """Update enrollment certificate URLs for many users in a course."""
    certificate_updates, error_response = _certificate_request_updates(request)
    if error_response:
        return error_response

    course = get_object_or_404(Course, slug=course_slug)
    updated, errors = _process_certificate_updates(
        course,
        course_slug,
        certificate_updates,
    )

    return _certificate_update_response(updated, errors)
