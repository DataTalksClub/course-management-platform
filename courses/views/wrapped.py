from django.contrib.auth import get_user_model
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, get_object_or_404

from courses.views.wrapped_context import (
    get_user_wrapped_statistics,
    shareable_user_wrapped_context,
    user_wrapped_no_activity_context,
    visible_wrapped_statistics,
    wrapped_no_data_context,
    wrapped_page_context,
)


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
        response = render(
            request,
            "courses/wrapped.html",
            context,
        )
        return response

    context = wrapped_page_context(request, year, wrapped_stats)
    response = render(
        request,
        "courses/wrapped.html",
        context,
    )
    return response


def user_wrapped_view(
    request: HttpRequest, year: int, student_id: int
) -> HttpResponse:
    """Individual user wrapped page for sharing on social media - only shows pre-calculated data"""
    User = get_user_model()
    user = get_object_or_404(User, id=student_id)

    user_wrapped = get_user_wrapped_statistics(year, user)
    if user_wrapped is None:
        context = user_wrapped_no_activity_context(year, user)
        response = render(
            request,
            "courses/user_wrapped.html",
            context,
        )
        return response

    context = shareable_user_wrapped_context(year, user, user_wrapped)
    response = render(
        request,
        "courses/user_wrapped.html",
        context,
    )
    return response
