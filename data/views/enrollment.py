"""
Enrollment-related data API views.

Provides views for managing enrollment certificates and retrieving graduates data.
"""

import json
from collections import Counter

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt

from accounts.auth import token_required

from courses.models import (
    User,
    Enrollment,
    Course,
    ProjectSubmission,
)


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
        name = enrollment.certificate_name or enrollment.display_name

        graduates.append(
            {
                "email": email,
                "name": name,
            }
        )

    response = {"graduates": graduates}
    return JsonResponse(response)


@token_required
@csrf_exempt
def bulk_update_enrollment_certificates_view(request, course_slug: str):
    """
    Update enrollment certificate URLs for many users in a course.

    Expected JSON payload:
    {
        "certificates": [
            {
                "email": "user@example.com",
                "certificate_path": "/path/to/certificate.pdf"
            }
        ]
    }

    A bare JSON array with the same objects is also accepted.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    if isinstance(data, list):
        certificate_updates = data
    elif isinstance(data, dict):
        certificate_updates = data.get("certificates")
    else:
        certificate_updates = None

    if not isinstance(certificate_updates, list):
        return JsonResponse(
            {"error": "Expected a certificates array"},
            status=400,
        )

    if not certificate_updates:
        return JsonResponse(
            {"error": "At least one certificate update is required"},
            status=400,
        )

    course = get_object_or_404(Course, slug=course_slug)
    valid_updates = []
    errors = []

    for index, update in enumerate(certificate_updates):
        if not isinstance(update, dict):
            errors.append(
                {
                    "index": index,
                    "code": "invalid_item",
                    "error": "Each certificate update must be an object",
                }
            )
            continue

        email = update.get("email")
        certificate_path = update.get("certificate_path")

        if not email or not certificate_path:
            errors.append(
                {
                    "index": index,
                    "email": email,
                    "code": "missing_fields",
                    "error": "Both email and certificate_path are required",
                }
            )
            continue

        valid_updates.append(
            {
                "index": index,
                "email": email,
                "certificate_path": certificate_path,
            }
        )

    emails = [update["email"] for update in valid_updates]
    users_by_email = {
        user.email: user
        for user in User.objects.filter(email__in=emails)
    }
    enrollments_by_email = {
        enrollment.student.email: enrollment
        for enrollment in Enrollment.objects.filter(
            course=course,
            student__email__in=emails,
        ).select_related("student")
    }

    enrollments_to_update = {}
    updated = []

    for update in valid_updates:
        email = update["email"]
        certificate_path = update["certificate_path"]

        if email not in users_by_email:
            errors.append(
                {
                    "index": update["index"],
                    "email": email,
                    "code": "user_not_found",
                    "error": f"User with email {email} not found",
                }
            )
            continue

        enrollment = enrollments_by_email.get(email)
        if enrollment is None:
            errors.append(
                {
                    "index": update["index"],
                    "email": email,
                    "code": "not_enrolled",
                    "error": f"User {email} is not enrolled in course {course_slug}",
                }
            )
            continue

        enrollment.certificate_url = certificate_path
        enrollments_to_update[enrollment.id] = enrollment
        updated.append(
            {
                "index": update["index"],
                "email": email,
                "enrollment_id": enrollment.id,
                "certificate_url": certificate_path,
            }
        )

    if enrollments_to_update:
        Enrollment.objects.bulk_update(
            enrollments_to_update.values(),
            ["certificate_url"],
        )

    return JsonResponse(
        {
            "success": len(errors) == 0,
            "updated_count": len(updated),
            "error_count": len(errors),
            "updated": updated,
            "errors": errors,
        }
    )
