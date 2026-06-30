from collections import defaultdict

from django.contrib import messages
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from courses.models import (
    Course,
    Enrollment,
    LeaderboardComplaint,
    ProjectSubmission,
    Submission,
)
from courses.services.enrollment_flags import (
    set_learning_in_public_disabled,
)

from .helpers import (
    paginate_queryset,
    pagination_querystring,
    staff_required,
)
from .view_models import enrollment_list_data


@staff_required
def enrollments_list(request, course_slug):
    """List all enrollments for a course"""
    course = get_object_or_404(Course, slug=course_slug)
    search_query = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "all")
    enrollments, enrollment_filter_counts = enrollment_list_data(
        course,
        search_query,
        status_filter,
    )

    enrollments_page = paginate_queryset(request, enrollments)
    total_enrollments = len(enrollments)
    querystring = pagination_querystring(request)

    context = {
        "course": course,
        "enrollments": enrollments_page.object_list,
        "enrollments_page": enrollments_page,
        "total_enrollments": total_enrollments,
        "enrollment_filter_counts": enrollment_filter_counts,
        "search_query": search_query,
        "status_filter": status_filter,
        "pagination_querystring": querystring,
    }

    return render(request, "cadmin/enrollments.html", context)


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
        complaints_by_enrollment[complaint.enrollment_id].append(
            complaint
        )
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


@staff_required
def leaderboard_complaints(request, course_slug):
    course = get_object_or_404(Course, slug=course_slug)
    context = leaderboard_complaints_context(course)
    return render(
        request,
        "cadmin/leaderboard_complaints.html",
        context,
    )


@staff_required
def leaderboard_complaint_resolve(request, course_slug, complaint_id):
    if request.method != "POST":
        return redirect(
            "cadmin_leaderboard_complaints", course_slug=course_slug
        )

    course = get_object_or_404(Course, slug=course_slug)
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
    return redirect(
        "cadmin_leaderboard_complaints", course_slug=course_slug
    )


def toggle_learning_in_public_response(
    request,
    enrollment,
    course_slug,
    enrollment_id,
):
    disabled = not enrollment.disable_learning_in_public
    set_learning_in_public_disabled(enrollment, disabled)
    enrollment.disable_learning_in_public = disabled

    if enrollment.disable_learning_in_public:
        messages.success(
            request,
            f"Learning in public disabled for {enrollment.student.username}. All scores zeroed out.",
        )
    else:
        messages.success(
            request,
            f"Learning in public re-enabled for {enrollment.student.username}. You may need to re-score homework and projects.",
        )

    return redirect(
        "cadmin_enrollment_edit",
        course_slug=course_slug,
        enrollment_id=enrollment_id,
    )


def enrollment_homework_submissions(enrollment):
    return (
        Submission.objects.filter(enrollment=enrollment)
        .select_related("homework")
        .order_by("-submitted_at")
    )


def enrollment_project_submissions(enrollment):
    return (
        ProjectSubmission.objects.filter(enrollment=enrollment)
        .select_related("project")
        .order_by("-submitted_at")
    )


def total_project_lip_score(project_submissions):
    total_score = 0
    for submission in project_submissions:
        project_score = submission.project_learning_in_public_score
        peer_review_score = submission.peer_review_learning_in_public_score
        total_score += project_score + peer_review_score
    return total_score


def total_homework_lip_score(homework_submissions):
    total_score = 0
    for submission in homework_submissions:
        total_score += submission.learning_in_public_score
    return total_score


def enrollment_edit_context(course, enrollment):
    homework_submissions = enrollment_homework_submissions(enrollment)
    project_submissions = enrollment_project_submissions(enrollment)
    homework_submissions_count = homework_submissions.count()
    project_submissions_count = project_submissions.count()
    total_homework_score = total_homework_lip_score(homework_submissions)
    total_project_score = total_project_lip_score(project_submissions)
    return {
        "course": course,
        "enrollment": enrollment,
        "homework_submissions": homework_submissions,
        "homework_submissions_count": homework_submissions_count,
        "project_submissions": project_submissions,
        "project_submissions_count": project_submissions_count,
        "total_homework_lip_score": total_homework_score,
        "total_project_lip_score": total_project_score,
    }


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
                enrollment,
                course_slug,
                enrollment_id,
            )

    context = enrollment_edit_context(course, enrollment)
    return render(
        request,
        "cadmin/enrollment_edit.html",
        context,
    )
