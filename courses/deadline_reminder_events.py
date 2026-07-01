from collections import OrderedDict

from django.urls import reverse

from course_management import email_templates
from course_management.datamailer.client import public_url
from course_management.deadlines import format_deadline_for_email
from courses.deadline_reminder_members import (
    reminder_members_from_enrollments,
    reminder_members_from_submissions,
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
from courses.deadline_reminder_types import (
    ReminderEvent,
    ReminderEventData,
    ReminderItemData,
    ReminderSpec,
    ReminderTemplateContextData,
)


def deadline_send_payload(
    config,
    *,
    event_key,
    template_context,
    metadata,
):
    payload = {
        "audience": config.audience,
        "client": config.client,
        "template_key": email_templates.DEADLINE_REMINDER,
        "category_tag": "deadline-reminders",
        "idempotency_key": event_key,
        "context": template_context,
        "metadata": metadata
        | {
            "source": "course-management-platform",
            "event": "deadline_reminder",
        },
    }
    if config.from_email:
        payload["from_email"] = config.from_email
    return payload


def transient_recipient_list_send_payload(event):
    return event.send_payload | {
        "list": {
            "key": event.list_key,
            "name": event.list_name,
            "metadata": event.list_metadata,
        },
        "members": event.members,
    }


def base_context(data):
    formatted_deadline = format_deadline_for_email(data.item.deadline)
    deadline_summary = formatted_deadline["deadline_summary"]
    profile_path = reverse("account_settings")
    profile_url = public_url(profile_path)

    return {
        "course_slug": data.item.course.slug,
        "course_title": data.item.course.title,
        "reminder_key": data.item.reminder_key,
        "item_type": data.spec.item_type,
        "item_slug": data.item.item_slug,
        "item_title": data.item.item_title,
        "deadline_at": deadline_summary,
        "deadline_iso": data.item.deadline.isoformat(),
        "action_url": data.action_url,
        "profile_url": profile_url,
        "notification_category": "deadline reminders",
        "notification_footer": (
            "You are receiving this because deadline reminders are "
            "enabled in your profile."
        ),
    }


def reminder_metadata(spec, item):
    return {
        "course_slug": item.course.slug,
        spec.metadata_slug_key: item.item_slug,
        spec.metadata_id_key: item.item_id,
        "reminder_key": item.reminder_key,
        "deadline_kind": spec.deadline_kind,
    }


def deadline_action_url(spec, item):
    action_path = reverse(
        spec.route_name,
        kwargs={
            "course_slug": item.course.slug,
            spec.route_slug_kwarg: item.item_slug,
        },
    )
    action_url = public_url(action_path)
    return action_url


def deadline_context(data):
    context = base_context(data)
    extra_context = data.item.context_extra(data.action_url)
    context.update(extra_context)
    return context


def reminder_event_send_payload(data, event_key, context):
    return deadline_send_payload(
        data.config,
        event_key=event_key,
        template_context=context,
        metadata=data.metadata,
    )


def reminder_event_context(data, action_url):
    context_data = ReminderTemplateContextData(
        spec=data.spec,
        item=data.item,
        action_url=action_url,
    )
    return deadline_context(context_data)


def build_reminder_event(data):
    item = data.item
    action_url = deadline_action_url(data.spec, item)
    event_key = reminder_event_key(
        data.spec,
        item.item_id,
        item.reminder_key,
    )
    context = reminder_event_context(data, action_url)
    list_key = reminder_list_key(
        data.spec,
        item,
    )
    list_name = reminder_list_name(
        data.spec,
        item,
    )
    send_payload = reminder_event_send_payload(data, event_key, context)
    return ReminderEvent(
        key=event_key,
        list_key=list_key,
        list_name=list_name,
        list_metadata=data.metadata,
        send_payload=send_payload,
        members=data.members,
    )


def reminder_event_key(spec, item_id, reminder_key):
    return f"deadline-reminder:{spec.event_kind}:{item_id}:{reminder_key}"


def reminder_list_key(spec, item):
    return (
        "deadline-reminders:"
        f"{spec.list_kind}:{item.course.slug}:"
        f"{item.item_slug}:{item.reminder_key}"
    )


def reminder_list_name(spec, item):
    return (
        f"{item.course.title} {item.item_title} "
        f"{item.reminder_key} {spec.list_name_suffix}"
    )


def homework_reminder_spec():
    return ReminderSpec(
        deadline_kind="homework",
        event_kind="homework",
        list_kind="homework",
        item_type="homework",
        route_name="homework",
        route_slug_kwarg="homework_slug",
        metadata_slug_key="homework_slug",
        metadata_id_key="homework_id",
        list_name_suffix="deadline reminders",
    )


def project_submission_reminder_spec():
    return ReminderSpec(
        deadline_kind="project_submission",
        event_kind="project",
        list_kind="project-submission",
        item_type="project",
        route_name="project",
        route_slug_kwarg="project_slug",
        metadata_slug_key="project_slug",
        metadata_id_key="project_id",
        list_name_suffix="submission deadline reminders",
    )


def peer_review_reminder_spec():
    return ReminderSpec(
        deadline_kind="peer_review",
        event_kind="peer-review",
        list_kind="peer-review",
        item_type="peer_review",
        route_name="projects_eval",
        route_slug_kwarg="project_slug",
        metadata_slug_key="project_slug",
        metadata_id_key="project_id",
        list_name_suffix="peer review deadline reminders",
    )


def homework_deadline_context(homework):
    return lambda action_url: {
        "homework_slug": homework.slug,
        "homework_title": homework.title,
        "homework_due_at": homework.due_date.isoformat(),
        "email_subject": f"Homework deadline soon: {homework.title}",
        "email_preview": "Your homework deadline is within 24 hours.",
        "intro_text": (
            f"{homework.title} in {homework.course.title} "
            "is due within 24 hours."
        ),
        "action_text": f"Submit or update homework: {action_url}",
    }


def project_submission_deadline_context(project):
    return lambda action_url: {
        "project_slug": project.slug,
        "project_title": project.title,
        "project_due_at": project.submission_due_date.isoformat(),
        "email_subject": f"Project deadline soon: {project.title}",
        "email_preview": "Your project submission deadline is coming up.",
        "intro_text": f"{project.title} in {project.course.title} is due soon.",
        "action_text": f"Submit or update project: {action_url}",
    }


def peer_review_deadline_context(project):
    return lambda action_url: {
        "project_slug": project.slug,
        "project_title": project.title,
        "peer_review_due_at": project.peer_review_due_date.isoformat(),
        "email_subject": f"Peer review deadline soon: {project.title}",
        "email_preview": (
            "Your assigned peer reviews are due within 24 hours."
        ),
        "intro_text": (
            f"Your assigned peer reviews for {project.title} "
            f"in {project.course.title} are due within 24 hours."
        ),
        "action_text": f"Complete peer reviews: {action_url}",
    }


def homework_reminder_item(homework):
    context_extra = homework_deadline_context(homework)
    return ReminderItemData(
        course=homework.course,
        item_slug=homework.slug,
        item_id=homework.pk,
        item_title=homework.title,
        reminder_key="24h",
        deadline=homework.due_date,
        context_extra=context_extra,
    )


def project_submission_reminder_item(project, reminder_key):
    context_extra = project_submission_deadline_context(project)
    return ReminderItemData(
        course=project.course,
        item_slug=project.slug,
        item_id=project.pk,
        item_title=project.title,
        reminder_key=reminder_key,
        deadline=project.submission_due_date,
        context_extra=context_extra,
    )


def peer_review_reminder_item(project):
    context_extra = peer_review_deadline_context(project)
    return ReminderItemData(
        course=project.course,
        item_slug=project.slug,
        item_id=project.pk,
        item_title=project.title,
        reminder_key="24h",
        deadline=project.peer_review_due_date,
        context_extra=context_extra,
    )


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
