from dataclasses import dataclass

from django.urls import reverse

from courses.models.course import Course
from courses.models.homework import Homework
from courses.models.project import Project
from courses.views.calendar_ics import (
    CalendarEventData,
    calendar_event,
    escape_ics_text,
)


@dataclass(frozen=True)
class ProjectDeadlineEventSpec:
    uid_suffix: str
    event_type: str
    deadline: object


@dataclass(frozen=True)
class ProjectDeadlineCalendarEventData:
    course: Course
    project: Project
    deadline: ProjectDeadlineEventSpec
    url: str
    dtstamp: object


def homework_calendar_events(request, course, dtstamp) -> list[list[str]]:
    homeworks = Homework.objects.filter(course=course).order_by("due_date")
    events = []
    for homework in homeworks:
        homework_path = reverse(
            "homework",
            kwargs={
                "course_slug": course.slug,
                "homework_slug": homework.slug,
            },
        )
        url = request.build_absolute_uri(homework_path)
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
    project_path = reverse(
        "project",
        kwargs={
            "course_slug": course.slug,
            "project_slug": project.slug,
        },
    )
    return request.build_absolute_uri(project_path)


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


def _project_deadline_specs(project):
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
    return deadlines


def _project_deadline_calendar_events(
    course, project, url, dtstamp
) -> list[list[str]]:
    deadlines = _project_deadline_specs(project)
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


def project_calendar_events(request, course, dtstamp) -> list[list[str]]:
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


def course_calendar_event_lines(request, course, dtstamp) -> list[str]:
    nested_events = []
    homework_events = homework_calendar_events(request, course, dtstamp)
    nested_events.extend(homework_events)
    project_events = project_calendar_events(request, course, dtstamp)
    nested_events.extend(project_events)

    events = []
    for event_lines in nested_events:
        for line in event_lines:
            events.append(line)
    return events


def course_calendar_lines(course, events):
    course_title = escape_ics_text(course.title)
    return [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//DataTalks.Club//Course Management Platform//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{course_title} deadlines",
        *events,
        "END:VCALENDAR",
    ]
