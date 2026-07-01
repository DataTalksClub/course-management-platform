from collections import Counter

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from accounts.auth import token_required
from courses.models import Course, ProjectSubmission


@require_GET
@token_required
def graduates_data_view(request, course_slug: str):
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
        graduate_record = {
            "email": email,
            "name": name,
        }
        graduates.append(graduate_record)

    response = {"graduates": graduates}
    json_response = JsonResponse(response)
    return json_response


def get_passed_enrollments(passed_project_submissions, min_projects):
    assert min_projects > 0, "min_projects must be greater than 0"

    counter_passed = Counter()
    ids_mapping = {}

    for submission in passed_project_submissions:
        enrollment = submission.enrollment
        enrollment_id = enrollment.id
        counter_passed[enrollment_id] += 1
        ids_mapping[enrollment_id] = enrollment

    passed_enrollments = []
    for enrollment_id, count in counter_passed.items():
        if count >= min_projects:
            enrollment = ids_mapping[enrollment_id]
            passed_enrollments.append(enrollment)

    return passed_enrollments
