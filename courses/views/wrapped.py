# uv run python -m scripts.wrapped

import logging
from typing import Dict, Any
from datetime import datetime

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.db.models import Sum, Count, Q
from django.utils import timezone

from courses.models import (
    Enrollment,
    Submission,
    ProjectSubmission,
)
from courses.models.project import PeerReview

logger = logging.getLogger(__name__)


def get_year_date_range(year=2025):
    """Get the start and end date for a given year"""
    year_start = timezone.make_aware(datetime(year, 1, 1))
    year_end = timezone.make_aware(datetime(year, 12, 31, 23, 59, 59))
    return year_start, year_end


def calculate_total_hours(
    homework_submissions_aggregate, project_submissions_aggregate
):
    """Calculate total hours from homework and project submissions"""
    total_hours = 0
    if homework_submissions_aggregate["total_lecture_hours"]:
        total_hours += homework_submissions_aggregate[
            "total_lecture_hours"
        ]
    if homework_submissions_aggregate["total_homework_hours"]:
        total_hours += homework_submissions_aggregate[
            "total_homework_hours"
        ]
    if project_submissions_aggregate["total_project_hours"]:
        total_hours += project_submissions_aggregate[
            "total_project_hours"
        ]
    return total_hours


def get_platform_statistics_2025() -> Dict[str, Any]:
    """Calculate platform-wide statistics for 2025"""
    year_start, year_end = get_year_date_range(year=2025)

    # Get enrollments in 2025
    enrollments_2025 = Enrollment.objects.filter(
        enrollment_date__gte=year_start, enrollment_date__lte=year_end
    )

    total_participants = (
        enrollments_2025.values("student").distinct().count()
    )

    # Get course popularity - enrollments per course in 2025
    course_stats = (
        enrollments_2025.values("course__title", "course__slug")
        .annotate(enrollment_count=Count("id"))
        .order_by("-enrollment_count")
    )

    # Calculate total hours spent in 2025
    # Homework hours
    homework_submissions_2025 = Submission.objects.filter(
        submitted_at__gte=year_start, submitted_at__lte=year_end
    ).aggregate(
        total_lecture_hours=Sum("time_spent_lectures"),
        total_homework_hours=Sum("time_spent_homework"),
    )

    # Project hours
    project_submissions_2025 = ProjectSubmission.objects.filter(
        submitted_at__gte=year_start, submitted_at__lte=year_end
    ).aggregate(total_project_hours=Sum("time_spent"))

    total_hours = calculate_total_hours(
        homework_submissions_2025, project_submissions_2025
    )

    # Count certificates (enrollments with certificate_url in 2025)
    total_certificates = enrollments_2025.exclude(
        Q(certificate_url__isnull=True) | Q(certificate_url="")
    ).count()

    # Total points earned in 2025
    total_points = (
        enrollments_2025.aggregate(total_score=Sum("total_score"))[
            "total_score"
        ]
        or 0
    )

    return {
        "total_participants": total_participants,
        "total_enrollments": enrollments_2025.count(),
        "course_stats": list(course_stats),
        "total_hours": round(total_hours, 1) if total_hours else 0,
        "total_certificates": total_certificates,
        "total_points": total_points,
    }


def get_comprehensive_user_statistics_2025(user) -> Dict[str, Any]:
    """
    Calculate comprehensive user-specific statistics for 2025.
    Includes users who have any homework or project activity in 2025,
    even if the course started in 2024 or hasn't finished.
    """
    year_start, year_end = get_year_date_range(year=2025)

    # Get all homework submissions in 2025
    homework_submissions_2025 = Submission.objects.filter(
        student=user,
        submitted_at__gte=year_start,
        submitted_at__lte=year_end,
    ).select_related("homework", "homework__course", "enrollment")

    # Get all project submissions in 2025
    project_submissions_2025 = ProjectSubmission.objects.filter(
        student=user,
        submitted_at__gte=year_start,
        submitted_at__lte=year_end,
    ).select_related("project", "project__course", "enrollment")

    # Get unique courses from submissions (courses with activity in 2025)
    courses_from_homeworks = set(
        hw.homework.course for hw in homework_submissions_2025
    )
    courses_from_projects = set(
        proj.project.course for proj in project_submissions_2025
    )
    courses_with_2025_activity = (
        courses_from_homeworks | courses_from_projects
    )

    # Get enrollments for these courses
    enrollments = Enrollment.objects.filter(
        student=user, course__in=courses_with_2025_activity
    ).select_related("course")

    # Total points from enrollments
    total_points = (
        enrollments.aggregate(total_score=Sum("total_score"))[
            "total_score"
        ]
        or 0
    )

    # Courses with activity
    courses_list = [
        {
            "title": e.course.title,
            "score": e.total_score,
            "slug": e.course.slug,
            "enrollment_id": e.id,
        }
        for e in enrollments
    ]

    # Calculate hours spent
    homework_hours = homework_submissions_2025.aggregate(
        total_lecture_hours=Sum("time_spent_lectures"),
        total_homework_hours=Sum("time_spent_homework"),
    )

    project_hours = project_submissions_2025.aggregate(
        total_project_hours=Sum("time_spent")
    )

    total_hours = calculate_total_hours(homework_hours, project_hours)

    # Count submissions
    homework_count = homework_submissions_2025.count()
    project_count = project_submissions_2025.count()

    # Count peer reviews done in 2025
    peer_reviews_given = PeerReview.objects.filter(
        reviewer__student=user,
        submitted_at__gte=year_start,
        submitted_at__lte=year_end,
    ).count()

    # Learning in public contributions
    lip_homework = sum(
        len(hw.learning_in_public_links)
        if hw.learning_in_public_links
        else 0
        for hw in homework_submissions_2025
    )
    lip_projects = sum(
        len(proj.learning_in_public_links)
        if proj.learning_in_public_links
        else 0
        for proj in project_submissions_2025
    )
    learning_in_public_count = lip_homework + lip_projects

    # FAQ contributions (non-empty)
    faq_homework = sum(
        1
        for hw in homework_submissions_2025
        if hw.faq_contribution and hw.faq_contribution.strip()
    )
    faq_projects = sum(
        1
        for proj in project_submissions_2025
        if proj.faq_contribution and proj.faq_contribution.strip()
    )
    faq_contributions_count = faq_homework + faq_projects

    # Certificates earned
    certificates_earned = enrollments.exclude(
        Q(certificate_url__isnull=True) | Q(certificate_url="")
    ).count()

    return {
        "total_points": total_points,
        "courses": courses_list,
        "total_hours": round(total_hours, 1) if total_hours else 0,
        "homework_count": homework_count,
        "project_count": project_count,
        "peer_reviews_given": peer_reviews_given,
        "learning_in_public_count": learning_in_public_count,
        "faq_contributions_count": faq_contributions_count,
        "certificates_earned": certificates_earned,
        "has_activity": homework_count > 0 or project_count > 0,
    }


def get_user_statistics_2025(user) -> Dict[str, Any]:
    """Calculate user-specific statistics for 2025"""
    year_start, year_end = get_year_date_range(year=2025)

    # Get user's enrollments in 2025
    user_enrollments = Enrollment.objects.filter(
        student=user,
        enrollment_date__gte=year_start,
        enrollment_date__lte=year_end,
    ).select_related("course")

    # Total points
    total_points = (
        user_enrollments.aggregate(total_score=Sum("total_score"))[
            "total_score"
        ]
        or 0
    )

    # Courses enrolled
    courses_enrolled = [
        {
            "title": e.course.title,
            "score": e.total_score,
            "slug": e.course.slug,
            "enrollment_id": e.id,
        }
        for e in user_enrollments
    ]

    # Calculate hours spent
    homework_submissions = Submission.objects.filter(
        student=user,
        submitted_at__gte=year_start,
        submitted_at__lte=year_end,
    ).aggregate(
        total_lecture_hours=Sum("time_spent_lectures"),
        total_homework_hours=Sum("time_spent_homework"),
    )

    project_submissions = ProjectSubmission.objects.filter(
        student=user,
        submitted_at__gte=year_start,
        submitted_at__lte=year_end,
    ).aggregate(total_project_hours=Sum("time_spent"))

    total_hours = calculate_total_hours(
        homework_submissions, project_submissions
    )

    # Count certificates
    certificates_earned = user_enrollments.exclude(
        Q(certificate_url__isnull=True) | Q(certificate_url="")
    ).count()

    return {
        "total_points": total_points,
        "courses_enrolled": courses_enrolled,
        "total_hours": round(total_hours, 1) if total_hours else 0,
        "certificates_earned": certificates_earned,
    }


def get_2025_leaderboard(limit=100):
    """Get top participants for 2025 (limited to 100)"""
    year_start, year_end = get_year_date_range(year=2025)

    # Get all enrollments from 2025, ordered by total score
    # We'll aggregate by student and sum their scores across all courses
    leaderboard = (
        Enrollment.objects.filter(
            enrollment_date__gte=year_start,
            enrollment_date__lte=year_end,
            display_on_leaderboard=True,
        )
        .values("student_id", "display_name", "student__email")
        .annotate(total_score=Sum("total_score"))
        .order_by("-total_score")[:limit]
    )

    # Add rank
    ranked_leaderboard = []
    for idx, entry in enumerate(leaderboard, start=1):
        ranked_leaderboard.append(
            {
                "rank": idx,
                "display_name": entry["display_name"],
                "total_score": entry["total_score"],
                "student_id": entry["student_id"],
            }
        )

    return ranked_leaderboard


def wrapped_view(request: HttpRequest, year: int) -> HttpResponse:
    """
    Main view for DataTalks.Club Wrapped - only shows pre-calculated statistics.

    Args:
        year: The year to display wrapped statistics for

    Note: Only displays data if WrappedStatistics exists with is_visible=True
    """
    from courses.models import WrappedStatistics, UserWrappedStatistics
    from django.shortcuts import render

    # Get pre-calculated wrapped statistics (only show if is_visible=True)
    try:
        wrapped_stats = WrappedStatistics.objects.get(
            year=year, is_visible=True
        )
    except WrappedStatistics.DoesNotExist:
        # No wrapped data available yet
        context = {
            "year": year,
            "no_data": True,
        }
        return render(request, "courses/wrapped.html", context)

    # Use pre-calculated statistics
    platform_stats = {
        "total_participants": wrapped_stats.total_participants,
        "total_enrollments": wrapped_stats.total_enrollments,
        "course_stats": wrapped_stats.course_stats[:4]
        if wrapped_stats.course_stats
        else [],
        "total_hours": wrapped_stats.total_hours,
        "total_certificates": wrapped_stats.total_certificates,
        "total_points": wrapped_stats.total_points,
    }
    leaderboard = wrapped_stats.leaderboard

    # Get user statistics if authenticated
    user_stats = None
    user_rank = None
    if request.user.is_authenticated:
        try:
            user_wrapped = UserWrappedStatistics.objects.get(
                wrapped=wrapped_stats, user=request.user
            )
            user_stats = {
                "total_points": user_wrapped.total_points,
                "courses_enrolled": user_wrapped.courses,
                "total_hours": user_wrapped.total_hours
                if user_wrapped.total_hours > 0
                else "N/A",
                "certificates_earned": user_wrapped.certificates_earned,
            }
            user_rank = user_wrapped.rank
        except UserWrappedStatistics.DoesNotExist:
            # User has no activity in this year
            pass

    context = {
        "year": year,
        "platform_stats": platform_stats,
        "user_stats": user_stats,
        "user_rank": user_rank,
        "leaderboard": leaderboard,
        "no_data": False,
    }

    return render(request, "courses/wrapped.html", context)


def user_wrapped_view(
    request: HttpRequest, year: int, student_id: int
) -> HttpResponse:
    """Individual user wrapped page for sharing on social media - only shows pre-calculated data"""
    from django.contrib.auth import get_user_model
    from django.shortcuts import get_object_or_404
    from courses.models import WrappedStatistics, UserWrappedStatistics

    User = get_user_model()
    user = get_object_or_404(User, id=student_id)

    # Get pre-calculated statistics (only show if is_visible=True)
    try:
        wrapped_stats = WrappedStatistics.objects.get(
            year=year, is_visible=True
        )
        user_wrapped = UserWrappedStatistics.objects.get(
            wrapped=wrapped_stats, user=user
        )
    except (
        WrappedStatistics.DoesNotExist,
        UserWrappedStatistics.DoesNotExist,
    ):
        # No wrapped data available for this user
        context = {
            "year": year,
            "user": user,
            "no_activity": True,
        }
        return render(request, "courses/user_wrapped.html", context)

    user_stats = {
        "total_points": user_wrapped.total_points,
        "courses": user_wrapped.courses,
        "total_hours": user_wrapped.total_hours
        if user_wrapped.total_hours > 0
        else "N/A",
        "homework_count": user_wrapped.homework_count,
        "project_count": user_wrapped.project_count,
        "peer_reviews_given": user_wrapped.peer_reviews_given,
        "learning_in_public_count": user_wrapped.learning_in_public_count,
        "faq_contributions_count": user_wrapped.faq_contributions_count,
        "certificates_earned": user_wrapped.certificates_earned,
        "has_activity": True,
    }

    # Prepare Twitter sharing text
    twitter_text = f"Check out my @DataTalksClub Wrapped {year}! I earned {user_wrapped.total_points} points"
    if user_wrapped.total_hours and user_wrapped.total_hours > 0:
        twitter_text += (
            f" and spent {user_wrapped.total_hours} hours learning"
        )
    twitter_text += "!"

    context = {
        "year": year,
        "viewed_user": user,
        "display_name": user_wrapped.display_name,
        "user_stats": user_stats,
        "user_rank": user_wrapped.rank,
        "twitter_text": twitter_text,
        "no_activity": False,
    }

    return render(request, "courses/user_wrapped.html", context)
