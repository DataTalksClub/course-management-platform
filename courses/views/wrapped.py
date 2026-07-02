from django.contrib.auth import get_user_model
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, get_object_or_404

from courses.views.wrapped_context import (
    get_user_wrapped_statistics,
    shareable_user_wrapped_context,
    visible_wrapped_statistics,
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
        context = {
            "year": year,
            "no_data": True,
        }
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
    User = get_user_model()
    user = get_object_or_404(User, id=student_id)

    user_wrapped = get_user_wrapped_statistics(year, user)
    if user_wrapped is None:
        display_name = user.get_username()
        context = {
            "year": year,
            "user": user,
            "viewed_user": user,
            "display_name": display_name,
            "no_activity": True,
        }
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
