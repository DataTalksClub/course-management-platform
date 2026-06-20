from django.contrib.auth import get_user_model
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, get_object_or_404

from courses.models import WrappedStatistics, UserWrappedStatistics


def wrapped_view(request: HttpRequest, year: int) -> HttpResponse:
    """
    Main view for DataTalks.Club Wrapped - only shows pre-calculated statistics.

    Args:
        year: The year to display wrapped statistics for

    Note: Only displays data if WrappedStatistics exists with is_visible=True
    """
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
