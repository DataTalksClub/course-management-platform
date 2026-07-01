from django.shortcuts import get_object_or_404, redirect, render

from courses.models import (
    Course,
    Enrollment,
)
from .enrollment_complaints import (
    leaderboard_complaints_context,
    resolve_leaderboard_complaint_response,
)
from .enrollment_edit import (
    enrollment_edit_context,
    toggle_learning_in_public_response,
)
from .enrollment_list import enrollments_list_context
from .helpers import (
    staff_required,
)


@staff_required
def enrollments_list(request, course_slug):
    """List all enrollments for a course"""
    course = get_object_or_404(Course, slug=course_slug)
    context = enrollments_list_context(request, course)
    response = render(request, "cadmin/enrollments.html", context)
    return response


@staff_required
def leaderboard_complaints(request, course_slug):
    course = get_object_or_404(Course, slug=course_slug)
    context = leaderboard_complaints_context(course)
    response = render(
        request,
        "cadmin/leaderboard_complaints.html",
        context,
    )
    return response


@staff_required
def leaderboard_complaint_resolve(request, course_slug, complaint_id):
    if request.method != "POST":
        response = redirect(
            "cadmin_leaderboard_complaints", course_slug=course_slug
        )
        return response

    course = get_object_or_404(Course, slug=course_slug)
    response = resolve_leaderboard_complaint_response(
        request,
        course,
        complaint_id,
    )
    return response


@staff_required
def enrollment_edit(request, course_slug, enrollment_id):
    """Edit an enrollment - mainly to disable learning in public"""
    course = get_object_or_404(Course, slug=course_slug)
    enrollment = get_object_or_404(
        Enrollment, id=enrollment_id, course=course
    )

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "toggle_learning_in_public":
            return toggle_learning_in_public_response(
                request,
                course,
                enrollment,
            )

    context = enrollment_edit_context(course, enrollment)
    response = render(
        request,
        "cadmin/enrollment_edit.html",
        context,
    )
    return response
