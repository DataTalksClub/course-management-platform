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
def update_enrollment_certificate_view(request, course_slug: str):
    """
    Update enrollment certificate URL for a user in a specific course.

    Expected JSON payload:
    {
        "email": "user@example.com",
        "certificate_path": "/path/to/certificate.pdf"
    }
    """
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)
        email = data.get("email")
        certificate_path = data.get("certificate_path")

        if not email or not certificate_path:
            return JsonResponse(
                {
                    "error": "Both email and certificate_path are required"
                },
                status=400,
            )

        # Find the course
        course = get_object_or_404(Course, slug=course_slug)

        # Find the user by email
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return JsonResponse(
                {"error": f"User with email {email} not found"},
                status=404,
            )

        # Find the enrollment
        try:
            enrollment = Enrollment.objects.get(
                student=user, course=course
            )
        except Enrollment.DoesNotExist:
            return JsonResponse(
                {
                    "error": f"User {email} is not enrolled in course {course_slug}"
                },
                status=404,
            )

        # Update the certificate URL
        enrollment.certificate_url = certificate_path
        enrollment.save()

        return JsonResponse(
            {
                "success": True,
                "message": f"Certificate URL updated for {email} in course {course_slug}",
                "enrollment_id": enrollment.id,
                "certificate_url": certificate_path,
            }
        )

    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
