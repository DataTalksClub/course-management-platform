from collections import OrderedDict

from courses.deadline_reminder_items import (
    homework_reminder_item,
    peer_review_reminder_item,
    project_submission_reminder_item,
)
from courses.deadline_reminder_members import (
    reminder_members_from_enrollments,
    reminder_members_from_submissions,
)
from courses.deadline_reminder_payloads import (
    build_reminder_event,
    reminder_metadata,
)
from courses.deadline_reminder_queries import (
    homework_reminder_queryset,
    matching_reminder_key,
    peer_review_reminder_queryset,
    pending_homework_enrollments,
    pending_peer_review_submissions,
    pending_project_submission_enrollments,
    project_submission_reminder_queryset,
    project_submission_reminder_windows,
)
from courses.deadline_reminder_specs import (
    homework_reminder_spec,
    peer_review_reminder_spec,
    project_submission_reminder_spec,
)
from courses.deadline_reminder_types import ReminderEventData


def homework_reminder_event(config, spec, homework):
    item = homework_reminder_item(homework)
    metadata = reminder_metadata(spec, item)
    pending_enrollments = pending_homework_enrollments(homework)
    members = reminder_members_from_enrollments(
        pending_enrollments,
        metadata,
        item.deadline,
    )
    if not members:
        return None
    event_data = ReminderEventData(
        config=config,
        spec=spec,
        item=item,
        members=members,
        metadata=metadata,
    )
    return build_reminder_event(event_data)


def project_submission_reminder_event(config, spec, project, reminder_key):
    item = project_submission_reminder_item(project, reminder_key)
    metadata = reminder_metadata(spec, item)
    pending_enrollments = pending_project_submission_enrollments(project)
    members = reminder_members_from_enrollments(
        pending_enrollments,
        metadata,
        item.deadline,
    )
    if not members:
        return None
    event_data = ReminderEventData(
        config=config,
        spec=spec,
        item=item,
        members=members,
        metadata=metadata,
    )
    return build_reminder_event(event_data)


def peer_review_reminder_event(config, spec, project):
    item = peer_review_reminder_item(project)
    metadata = reminder_metadata(spec, item)
    pending_submissions = pending_peer_review_submissions(project)
    members = reminder_members_from_submissions(
        pending_submissions,
        metadata,
        item.deadline,
    )
    if not members:
        return None
    event_data = ReminderEventData(
        config=config,
        spec=spec,
        item=item,
        members=members,
        metadata=metadata,
    )
    return build_reminder_event(event_data)


def homework_events(config, now, course_slug):
    spec = homework_reminder_spec()
    events = []
    homeworks = homework_reminder_queryset(now, course_slug)
    for homework in homeworks:
        event = homework_reminder_event(config, spec, homework)
        if event is not None:
            events.append(event)
    return events


def project_submission_events(config, now, course_slug):
    events = []
    spec = project_submission_reminder_spec()
    windows = project_submission_reminder_windows(now)
    projects = project_submission_reminder_queryset(
        windows,
        course_slug,
    )
    for project in projects:
        reminder_key = matching_reminder_key(
            project.submission_due_date,
            windows,
        )
        event = project_submission_reminder_event(
            config, spec, project, reminder_key
        )
        if event is not None:
            events.append(event)
    return events


def peer_review_events(config, now, course_slug):
    events = []
    spec = peer_review_reminder_spec()
    projects = peer_review_reminder_queryset(now, course_slug)
    for project in projects:
        event = peer_review_reminder_event(config, spec, project)
        if event is not None:
            events.append(event)
    return events


def build_reminder_events(config, now, course_slug=""):
    events = OrderedDict()
    reminder_events = []
    homework_reminder_events = homework_events(config, now, course_slug)
    for event in homework_reminder_events:
        reminder_events.append(event)
    project_reminder_events = project_submission_events(
        config,
        now,
        course_slug,
    )
    for event in project_reminder_events:
        reminder_events.append(event)
    peer_review_reminder_events = peer_review_events(
        config,
        now,
        course_slug,
    )
    for event in peer_review_reminder_events:
        reminder_events.append(event)

    for event in reminder_events:
        events[event.list_key] = event
    event_values = events.values()
    unique_events = list(event_values)
    return unique_events


def reminder_event_member_count(events):
    total_members = 0
    for event in events:
        total_members += len(event.members)
    return total_members
