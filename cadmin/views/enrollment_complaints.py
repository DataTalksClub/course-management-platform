from collections import defaultdict

from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone

from courses.models.course import Enrollment, LeaderboardComplaint


def complaint_enrollments(course):
    unresolved_complaints = Q(complaints__resolved=False)
    open_complaint_count = Count(
        "complaints",
        filter=unresolved_complaints,
    )
    total_complaint_count = Count("complaints")
    return (
        Enrollment.objects.filter(course=course)
        .select_related("student")
        .annotate(
            open_complaints=open_complaint_count,
            total_complaints=total_complaint_count,
        )
        .filter(total_complaints__gt=0)
        .order_by(
            "-open_complaints",
            "-total_complaints",
            "position_on_leaderboard",
        )
    )


def complaints_grouped_by_enrollment(course):
    complaints_by_enrollment = defaultdict(list)
    complaints = (
        LeaderboardComplaint.objects.filter(enrollment__course=course)
        .select_related("enrollment", "reporter", "resolved_by")
        .order_by("resolved", "-created_at")
    )
    for complaint in complaints:
        enrollment_id = complaint.enrollment_id
        complaints_by_enrollment[enrollment_id].append(complaint)
    return complaints_by_enrollment


def complaint_enrollment_rows(course):
    complaints_by_enrollment = complaints_grouped_by_enrollment(course)
    enrollment_rows = []
    enrollments = complaint_enrollments(course)
    for enrollment in enrollments:
        record = {
            "enrollment": enrollment,
            "complaints": complaints_by_enrollment[enrollment.id],
        }
        enrollment_rows.append(record)
    return enrollment_rows


def leaderboard_complaint_counts(course):
    complaints = LeaderboardComplaint.objects.filter(
        enrollment__course=course,
    )
    open_complaints_count = complaints.filter(
        resolved=False,
    ).count()
    total_complaints_count = complaints.count()
    return {
        "open_complaints_count": open_complaints_count,
        "total_complaints_count": total_complaints_count,
    }


def leaderboard_complaints_context(course):
    context = leaderboard_complaint_counts(course)
    enrollment_rows = complaint_enrollment_rows(course)
    context.update(
        {
            "course": course,
            "enrollment_rows": enrollment_rows,
        }
    )
    return context


def resolve_leaderboard_complaint_response(request, course, complaint_id):
    complaint = get_object_or_404(
        LeaderboardComplaint,
        id=complaint_id,
        enrollment__course=course,
    )
    complaint.resolved = True
    complaint.resolved_at = timezone.now()
    complaint.resolved_by = request.user
    complaint.save(
        update_fields=["resolved", "resolved_at", "resolved_by"]
    )

    messages.success(request, "Flag marked as resolved.")
    response = redirect(
        "cadmin_leaderboard_complaints", course_slug=course.slug
    )
    return response
