from dataclasses import dataclass
from datetime import timedelta, timezone as datetime_timezone

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone

from courses.models import Course, Homework, Project


@dataclass(frozen=True)
class ProjectDeadlineEventSpec:
    uid_suffix: str
    event_type: str
    deadline: object


@dataclass(frozen=True)
class CalendarEventData:
    uid: str
    summary: str
    start: object
    url: str
    description: str
    dtstamp: object


@dataclass(frozen=True)
class ProjectDeadlineCalendarEventData:
    course: Course
    project: Project
    deadline: ProjectDeadlineEventSpec
    url: str
    dtstamp: object


def escape_ics_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


def format_ics_datetime(value) -> str:
    if timezone.is_naive(value):
        value = timezone.make_aware(
            value, timezone.get_current_timezone()
        )

    value = value.astimezone(datetime_timezone.utc)
    return value.strftime("%Y%m%dT%H%M%SZ")


def calendar_event(data: CalendarEventData) -> list[str]:
    end = data.start + timedelta(minutes=30)

    return [
        "BEGIN:VEVENT",
        f"UID:{escape_ics_text(data.uid)}",
        f"DTSTAMP:{format_ics_datetime(data.dtstamp)}",
        f"DTSTART:{format_ics_datetime(data.start)}",
        f"DTEND:{format_ics_datetime(end)}",
        f"SUMMARY:{escape_ics_text(data.summary)}",
        f"DESCRIPTION:{escape_ics_text(data.description)}",
        f"URL:{escape_ics_text(data.url)}",
        "END:VEVENT",
    ]


def _homework_calendar_events(request, course, dtstamp) -> list[list[str]]:
    homeworks = Homework.objects.filter(course=course).order_by("due_date")
    events = []
    for homework in homeworks:
        url = request.build_absolute_uri(
            reverse(
                "homework",
                kwargs={
                    "course_slug": course.slug,
                    "homework_slug": homework.slug,
                },
            )
        )
        event_data = CalendarEventData(
            uid=f"homework-{homework.id}@courses.datatalks.club",
            summary=f"{course.title}: {homework.title} deadline",
            start=homework.due_date,
            url=url,
            description=(
                f"Homework deadline for {homework.title}. "
                f"Open the assignment: {url}"
            ),
            dtstamp=dtstamp,
        )
        event = calendar_event(event_data)
        events.append(event)
    return events


def _project_detail_url(request, course, project) -> str:
    return request.build_absolute_uri(
        reverse(
            "project",
            kwargs={
                "course_slug": course.slug,
                "project_slug": project.slug,
            },
        )
    )


def _project_deadline_calendar_event(
    data: ProjectDeadlineCalendarEventData,
) -> list[str]:
    event_data = CalendarEventData(
        uid=(
            f"project-{data.project.id}-{data.deadline.uid_suffix}"
            "@courses.datatalks.club"
        ),
        summary=(
            f"{data.course.title}: {data.project.title} "
            f"{data.deadline.event_type} deadline"
        ),
        start=data.deadline.deadline,
        url=data.url,
        description=(
            f"Project {data.deadline.event_type} deadline for "
            f"{data.project.title}. Open the project: {data.url}"
        ),
        dtstamp=data.dtstamp,
    )
    return calendar_event(event_data)


def _project_deadline_calendar_events(
    course, project, url, dtstamp
) -> list[list[str]]:
    submission_deadline = ProjectDeadlineEventSpec(
        uid_suffix="submission",
        event_type="submission",
        deadline=project.submission_due_date,
    )
    peer_review_deadline = ProjectDeadlineEventSpec(
        uid_suffix="peer-review",
        event_type="peer review",
        deadline=project.peer_review_due_date,
    )
    deadlines = (
        submission_deadline,
        peer_review_deadline,
    )
    events = []
    for deadline in deadlines:
        event_data = ProjectDeadlineCalendarEventData(
            course=course,
            project=project,
            deadline=deadline,
            url=url,
            dtstamp=dtstamp,
        )
        event = _project_deadline_calendar_event(event_data)
        events.append(event)
    return events


def _project_calendar_events(request, course, dtstamp) -> list[list[str]]:
    projects = Project.objects.filter(course=course).order_by(
        "submission_due_date",
        "peer_review_due_date",
    )
    events = []
    for project in projects:
        project_url = _project_detail_url(request, course, project)
        project_events = _project_deadline_calendar_events(
            course, project, project_url, dtstamp
        )
        events.extend(project_events)
    return events


def _course_calendar_lines(course, events):
    return [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//DataTalks.Club//Course Management Platform//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escape_ics_text(course.title)} deadlines",
        *events,
        "END:VCALENDAR",
    ]


def course_calendar_view(
    request: HttpRequest,
    course_slug: str,
) -> HttpResponse:
    course = get_object_or_404(Course, slug=course_slug, visible=True)
    dtstamp = timezone.now()
    nested_events = []
    homework_events = _homework_calendar_events(request, course, dtstamp)
    nested_events.extend(homework_events)
    project_events = _project_calendar_events(request, course, dtstamp)
    nested_events.extend(project_events)

    events = []
    for event_lines in nested_events:
        for line in event_lines:
            events.append(line)
    calendar_lines = _course_calendar_lines(course, events)

    response = HttpResponse(
        "\r\n".join(calendar_lines) + "\r\n",
        content_type="text/calendar; charset=utf-8",
    )
    response["Content-Disposition"] = (
        f'inline; filename="{course.slug}-deadlines.ics"'
    )
    return response
