import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from courses.models.course import (
    Course,
    Enrollment,
)
from courses.views.course_leaderboard_breakdown import (
    leaderboard_score_breakdown_context,
)
from courses.views.course_leaderboard_data import leaderboard_context

from .forms import LeaderboardComplaintForm

logger = logging.getLogger(__name__)


def leaderboard_view(request, course_slug: str):
    course = get_object_or_404(Course, slug=course_slug)
    page_number = request.GET.get("page")
    context = leaderboard_context(course, request.user, page_number)

    response = render(request, "courses/leaderboard.html", context)
    return response


def leaderboard_score_breakdown_view(
    request, course_slug: str, enrollment_id: int
):
    enrollments = Enrollment.objects.select_related("student", "course")
    enrollment = get_object_or_404(
        enrollments,
        id=enrollment_id,
        course__slug=course_slug,
    )
    context = leaderboard_score_breakdown_context(enrollment, request.user)

    response = render(
        request, "courses/leaderboard_score_breakdown.html", context
    )
    return response


def _save_leaderboard_complaint(form, enrollment, reporter):
    complaint = form.save(commit=False)
    complaint.enrollment = enrollment
    complaint.reporter = reporter
    complaint.save()


def _leaderboard_complaint_post_response(
    request,
    form,
    enrollment,
    course_slug,
):
    if not form.is_valid():
        return None

    _save_leaderboard_complaint(form, enrollment, request.user)
    messages.success(
        request,
        "Thanks. The course team will review this leaderboard record.",
    )
    response = redirect(
        "leaderboard_score_breakdown",
        course_slug=course_slug,
        enrollment_id=enrollment.id,
    )
    return response


def leaderboard_complaint_context(enrollment, form):
    context = {
        "enrollment": enrollment,
        "course": enrollment.course,
        "form": form,
    }
    return context


@login_required
def leaderboard_complaint_view(
    request, course_slug: str, enrollment_id: int
):
    enrollments = Enrollment.objects.select_related("course", "student")
    enrollment = get_object_or_404(
        enrollments,
        id=enrollment_id,
        course__slug=course_slug,
    )

    if request.method == "POST":
        form = LeaderboardComplaintForm(request.POST)
        response = _leaderboard_complaint_post_response(
            request,
            form,
            enrollment,
            course_slug,
        )
        if response is not None:
            return response
    else:
        form = LeaderboardComplaintForm()

    context = leaderboard_complaint_context(enrollment, form)
    response = render(
        request, "courses/leaderboard_complaint.html", context
    )
    return response
