from django.contrib.auth import get_user_model
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, get_object_or_404

from courses.models import WrappedStatistics, UserWrappedStatistics


def visible_wrapped_statistics(year: int) -> WrappedStatistics | None:
    try:
        return WrappedStatistics.objects.get(year=year, is_visible=True)
    except WrappedStatistics.DoesNotExist:
        return None


def wrapped_no_data_context(year: int) -> dict:
    return {
        "year": year,
        "no_data": True,
    }


def platform_stats_context(wrapped_stats: WrappedStatistics) -> dict:
    course_stats = wrapped_stats.course_stats[:4]
    if not wrapped_stats.course_stats:
        course_stats = []

    return {
        "total_participants": wrapped_stats.total_participants,
        "total_enrollments": wrapped_stats.total_enrollments,
        "course_stats": course_stats,
        "total_hours": wrapped_stats.total_hours,
        "total_certificates": wrapped_stats.total_certificates,
        "total_points": wrapped_stats.total_points,
    }


def wrapped_hours_label(total_hours: float):
    if total_hours > 0:
        return total_hours
    return "N/A"


def user_stats_context(user_wrapped: UserWrappedStatistics) -> dict:
    total_hours = wrapped_hours_label(user_wrapped.total_hours)
    return {
        "total_points": user_wrapped.total_points,
        "courses_enrolled": user_wrapped.courses,
        "total_hours": total_hours,
        "certificates_earned": user_wrapped.certificates_earned,
    }


def current_user_wrapped_context(request, wrapped_stats) -> dict:
    context = {
        "user_stats": None,
        "user_rank": None,
    }

    if not request.user.is_authenticated:
        return context

    try:
        user_wrapped = UserWrappedStatistics.objects.get(
            wrapped=wrapped_stats, user=request.user
        )
    except UserWrappedStatistics.DoesNotExist:
        return context

    context["user_stats"] = user_stats_context(user_wrapped)
    context["user_rank"] = user_wrapped.rank
    return context


def wrapped_page_context(request, year: int, wrapped_stats) -> dict:
    platform_stats = platform_stats_context(wrapped_stats)
    context = {
        "year": year,
        "platform_stats": platform_stats,
        "leaderboard": wrapped_stats.leaderboard,
        "no_data": False,
    }
    current_user_context = current_user_wrapped_context(
        request,
        wrapped_stats,
    )
    context.update(current_user_context)
    return context


def wrapped_view(request: HttpRequest, year: int) -> HttpResponse:
    """
    Main view for DataTalks.Club Wrapped - only shows pre-calculated statistics.

    Args:
        year: The year to display wrapped statistics for

    Note: Only displays data if WrappedStatistics exists with is_visible=True
    """
    wrapped_stats = visible_wrapped_statistics(year)
    if wrapped_stats is None:
        context = wrapped_no_data_context(year)
        return render(
            request,
            "courses/wrapped.html",
            context,
        )

    context = wrapped_page_context(request, year, wrapped_stats)
    return render(
        request,
        "courses/wrapped.html",
        context,
    )


def user_wrapped_no_activity_context(year: int, user) -> dict:
    display_name = user.get_username()
    return {
        "year": year,
        "user": user,
        "viewed_user": user,
        "display_name": display_name,
        "no_activity": True,
    }


def get_user_wrapped_statistics(year: int, user):
    wrapped_stats = visible_wrapped_statistics(year)
    if wrapped_stats is None:
        return None

    try:
        return UserWrappedStatistics.objects.get(
            wrapped=wrapped_stats, user=user
        )
    except UserWrappedStatistics.DoesNotExist:
        return None


def shareable_user_stats_context(
    user_wrapped: UserWrappedStatistics,
) -> dict:
    total_hours = wrapped_hours_label(user_wrapped.total_hours)
    return {
        "total_points": user_wrapped.total_points,
        "courses": user_wrapped.courses,
        "total_hours": total_hours,
        "homework_count": user_wrapped.homework_count,
        "project_count": user_wrapped.project_count,
        "peer_reviews_given": user_wrapped.peer_reviews_given,
        "learning_in_public_count": user_wrapped.learning_in_public_count,
        "faq_contributions_count": user_wrapped.faq_contributions_count,
        "certificates_earned": user_wrapped.certificates_earned,
        "has_activity": True,
    }


def wrapped_twitter_text(year: int, user_wrapped) -> str:
    text = (
        f"Check out my @DataTalksClub Wrapped {year}! "
        f"I earned {user_wrapped.total_points} points"
    )
    if user_wrapped.total_hours and user_wrapped.total_hours > 0:
        text += f" and spent {user_wrapped.total_hours} hours learning"
    return f"{text}!"


def shareable_user_wrapped_context(
    year: int, user, user_wrapped
) -> dict:
    user_stats = shareable_user_stats_context(user_wrapped)
    twitter_text = wrapped_twitter_text(year, user_wrapped)
    return {
        "year": year,
        "viewed_user": user,
        "display_name": user_wrapped.display_name,
        "user_stats": user_stats,
        "user_rank": user_wrapped.rank,
        "twitter_text": twitter_text,
        "no_activity": False,
    }


def user_wrapped_view(
    request: HttpRequest, year: int, student_id: int
) -> HttpResponse:
    """Individual user wrapped page for sharing on social media - only shows pre-calculated data"""
    User = get_user_model()
    user = get_object_or_404(User, id=student_id)

    user_wrapped = get_user_wrapped_statistics(year, user)
    if user_wrapped is None:
        context = user_wrapped_no_activity_context(year, user)
        return render(
            request,
            "courses/user_wrapped.html",
            context,
        )

    context = shareable_user_wrapped_context(year, user, user_wrapped)
    return render(
        request,
        "courses/user_wrapped.html",
        context,
    )
