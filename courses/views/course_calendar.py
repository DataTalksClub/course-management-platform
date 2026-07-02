from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone

from courses.models.course import Course
from courses.views.course_calendar_events import (
    course_calendar_event_lines,
    course_calendar_lines,
)


def course_calendar_view(
    request: HttpRequest,
    course_slug: str,
) -> HttpResponse:
    course = get_object_or_404(Course, slug=course_slug, visible=True)
    dtstamp = timezone.now()
    event_lines = course_calendar_event_lines(request, course, dtstamp)
    calendar_lines = course_calendar_lines(course, event_lines)
    response_body = "\r\n".join(calendar_lines) + "\r\n"

    response = HttpResponse(
        response_body,
        content_type="text/calendar; charset=utf-8",
    )
    response["Content-Disposition"] = (
        f'inline; filename="{course.slug}-deadlines.ics"'
    )
    return response
