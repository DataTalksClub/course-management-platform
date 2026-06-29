from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone as datetime_timezone
from typing import Any

import requests
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from course_management import email_templates
from course_management.datamailer import (
    DatamailerClient,
    DatamailerConfig,
    public_url,
    record_datamailer_send_audit,
)
from data.models import DatamailerSendAuditType
from course_management.deadlines import format_deadline_for_email
from courses.models import (
    Enrollment,
    Homework,
    HomeworkState,
    PeerReviewState,
    Project,
    ProjectState,
    ProjectSubmission,
    Submission,
)


@dataclass(frozen=True)
class ReminderEvent:
    key: str
    list_key: str
    list_name: str
    list_metadata: dict[str, Any]
    send_payload: dict[str, Any]
    members: list[dict[str, Any]]


@dataclass(frozen=True)
class ReminderSpec:
    deadline_kind: str
    event_kind: str
    list_kind: str
    item_type: str
    route_name: str
    route_slug_kwarg: str
    list_name_suffix: str


@dataclass(frozen=True)
class ReminderWindow:
    key: str
    start: datetime
    end: datetime


def aware_now(value: str):
    if not value:
        return timezone.now()

    parsed = parse_datetime(value)
    if parsed is None:
        raise CommandError("--now must be an ISO-8601 datetime.")
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(
            parsed, timezone.get_current_timezone()
        )
    return parsed


def utc_day_window(now, *, days_ahead):
    now_utc = now.astimezone(datetime_timezone.utc)
    target_date = (now_utc + timedelta(days=days_ahead)).date()
    start = datetime.combine(
        target_date,
        time.min,
        tzinfo=datetime_timezone.utc,
    )
    return start, start + timedelta(days=1)


def reminder_window(now, reminder_key):
    days_by_key = {
        "24h": 1,
        "7d": 8,
    }
    return utc_day_window(now, days_ahead=days_by_key[reminder_key])


def matching_reminder_key(deadline, windows):
    for window in windows:
        if is_within_window(deadline, window.start, window.end):
            return window.key
    return None


def is_within_window(value, start, end):
    value_utc = value.astimezone(datetime_timezone.utc)
    return start <= value_utc < end


def deadline_metadata(deadline, user):
    formatted = format_deadline_for_email(deadline, user)
    return {
        "deadline_at": formatted["deadline_summary"],
        "deadline_iso": formatted["deadline_iso"],
        "deadline_weekday": formatted["deadline_weekday"],
        "deadline_date": formatted["deadline_date"],
        "deadline_time": formatted["deadline_time"],
        "deadline_timezone": formatted["deadline_timezone"],
        "deadline_summary": formatted["deadline_summary"],
    }


def member_from_enrollment(enrollment, metadata, *, deadline=None):
    email = (enrollment.student.email or "").strip().lower()
    if not email:
        return None
    member_metadata = metadata
    if deadline is not None:
        member_metadata = member_metadata | deadline_metadata(
            deadline, enrollment.student
        )
    return {
        "source_object_key": f"enrollment:{enrollment.pk}",
        "email": email,
        "status": "active",
        "metadata": member_metadata
        | {
            "enrollment_id": enrollment.pk,
            "user_id": enrollment.student_id,
            "source_object_key": f"enrollment:{enrollment.pk}",
        },
    }


def member_from_project_submission(submission, metadata, *, deadline=None):
    email = (submission.student.email or "").strip().lower()
    if not email:
        return None
    source_object_key = f"project-submission:{submission.pk}"
    member_metadata = metadata
    if deadline is not None:
        member_metadata = member_metadata | deadline_metadata(
            deadline, submission.student
        )
    return {
        "source_object_key": source_object_key,
        "email": email,
        "status": "active",
        "metadata": member_metadata
        | {
            "submission_id": submission.pk,
            "enrollment_id": submission.enrollment_id,
            "user_id": submission.student_id,
            "source_object_key": source_object_key,
        },
    }


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


def base_context(
    course,
    *,
    reminder_key,
    item_type,
    item_slug,
    item_title,
    deadline,
    action_url,
):
    return {
        "course_slug": course.slug,
        "course_title": course.title,
        "reminder_key": reminder_key,
        "item_type": item_type,
        "item_slug": item_slug,
        "item_title": item_title,
        "deadline_at": format_deadline_for_email(deadline)["deadline_summary"],
        "deadline_iso": deadline.isoformat(),
        "action_url": action_url,
        "profile_url": public_url(reverse("account_settings")),
        "notification_category": "deadline reminders",
        "notification_footer": (
            "You are receiving this because deadline reminders are "
            "enabled in your profile."
        ),
    }


def reminder_metadata(
    course,
    *,
    item_slug_key,
    item_slug,
    item_id_key,
    item_id,
    reminder_key,
    deadline_kind,
):
    return {
        "course_slug": course.slug,
        item_slug_key: item_slug,
        item_id_key: item_id,
        "reminder_key": reminder_key,
        "deadline_kind": deadline_kind,
    }


def deadline_action_url(spec, course, item_slug):
    return public_url(
        reverse(
            spec.route_name,
            kwargs={
                "course_slug": course.slug,
                spec.route_slug_kwarg: item_slug,
            },
        )
    )


def deadline_context(
    course,
    *,
    reminder_key,
    item_type,
    item_slug,
    item_title,
    deadline,
    action_url,
    extra_context,
):
    context = base_context(
        course,
        reminder_key=reminder_key,
        item_type=item_type,
        item_slug=item_slug,
        item_title=item_title,
        deadline=deadline,
        action_url=action_url,
    )
    context.update(extra_context)
    return context


def build_reminder_event(
    config,
    spec,
    *,
    course,
    item_id,
    item_slug,
    item_title,
    reminder_key,
    deadline,
    members,
    metadata,
    context_extra,
):
    action_url = deadline_action_url(spec, course, item_slug)
    event_key = reminder_event_key(spec, item_id, reminder_key)
    context = reminder_template_context(
        spec, course, item_slug, item_title,
        reminder_key, deadline, action_url, context_extra,
    )
    return ReminderEvent(
        key=event_key,
        list_key=reminder_list_key(spec, course, item_slug, reminder_key),
        list_name=reminder_list_name(
            spec,
            course,
            item_title,
            reminder_key,
        ),
        list_metadata=metadata,
        send_payload=deadline_send_payload(
            config,
            event_key=event_key,
            template_context=context,
            metadata=metadata,
        ),
        members=members,
    )


def reminder_template_context(
    spec,
    course,
    item_slug,
    item_title,
    reminder_key,
    deadline,
    action_url,
    context_extra,
):
    return deadline_context(
        course,
        reminder_key=reminder_key,
        item_type=spec.item_type,
        item_slug=item_slug,
        item_title=item_title,
        deadline=deadline,
        action_url=action_url,
        extra_context=context_extra(action_url),
    )


def reminder_event_key(spec, item_id, reminder_key):
    return f"deadline-reminder:{spec.event_kind}:{item_id}:{reminder_key}"


def reminder_list_key(spec, course, item_slug, reminder_key):
    return (
        "deadline-reminders:"
        f"{spec.list_kind}:{course.slug}:{item_slug}:{reminder_key}"
    )


def reminder_list_name(spec, course, item_title, reminder_key):
    return f"{course.title} {item_title} {reminder_key} {spec.list_name_suffix}"


def homework_reminder_spec():
    return ReminderSpec(
        deadline_kind="homework",
        event_kind="homework",
        list_kind="homework",
        item_type="homework",
        route_name="homework",
        route_slug_kwarg="homework_slug",
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
        list_name_suffix="peer review deadline reminders",
    )


def homework_reminder_queryset(now, course_slug):
    reminder_start, reminder_end = reminder_window(now, "24h")
    queryset = Homework.objects.select_related("course").filter(
        state=HomeworkState.OPEN.value,
        due_date__gte=reminder_start,
        due_date__lt=reminder_end,
    )
    if course_slug:
        queryset = queryset.filter(course__slug=course_slug)
    return queryset.order_by("due_date", "pk")


def project_submission_reminder_windows(now):
    daily_start, daily_end = reminder_window(now, "24h")
    weekly_start, weekly_end = reminder_window(now, "7d")
    return (
        ReminderWindow("24h", daily_start, daily_end),
        ReminderWindow("7d", weekly_start, weekly_end),
    )


def project_submission_reminder_queryset(windows, course_slug):
    daily_window = windows[0]
    weekly_window = windows[1]
    queryset = Project.objects.select_related("course").filter(
        state=ProjectState.COLLECTING_SUBMISSIONS.value,
    ).filter(
        Q(
            submission_due_date__gte=daily_window.start,
            submission_due_date__lt=daily_window.end,
        )
        | Q(
            submission_due_date__gte=weekly_window.start,
            submission_due_date__lt=weekly_window.end,
        )
    )
    if course_slug:
        queryset = queryset.filter(course__slug=course_slug)
    return queryset.order_by("submission_due_date", "pk")


def peer_review_reminder_queryset(now, course_slug):
    reminder_start, reminder_end = reminder_window(now, "24h")
    queryset = Project.objects.select_related("course").filter(
        state=ProjectState.PEER_REVIEWING.value,
        peer_review_due_date__gte=reminder_start,
        peer_review_due_date__lt=reminder_end,
    )
    if course_slug:
        queryset = queryset.filter(course__slug=course_slug)
    return queryset.order_by("peer_review_due_date", "pk")


def pending_homework_enrollments(homework):
    submitted_student_ids = Submission.objects.filter(
        homework=homework
    ).values("student_id")
    return (
        Enrollment.objects.filter(course=homework.course)
        .exclude(student_id__in=submitted_student_ids)
        .select_related("student", "course")
        .order_by("pk")
    )


def pending_project_submission_enrollments(project):
    submitted_student_ids = ProjectSubmission.objects.filter(
        project=project,
        volunteer_review_only=False,
    ).values("student_id")
    return (
        Enrollment.objects.filter(course=project.course)
        .exclude(student_id__in=submitted_student_ids)
        .select_related("student", "course")
        .order_by("pk")
    )


def pending_peer_review_submissions(project):
    return (
        ProjectSubmission.objects.filter(
            project=project,
            volunteer_review_only=False,
            reviewers__state=PeerReviewState.TO_REVIEW.value,
            reviewers__optional=False,
        )
        .filter(Q(student__email__isnull=False) & ~Q(student__email=""))
        .select_related("student", "enrollment", "project")
        .distinct()
        .order_by("pk")
    )


def reminder_members_from_enrollments(enrollments, metadata, deadline):
    members = []
    for enrollment in enrollments:
        member = member_from_enrollment(
            enrollment,
            metadata,
            deadline=deadline,
        )
        if member is not None:
            members.append(member)
    return members


def reminder_members_from_submissions(submissions, metadata, deadline):
    members = []
    for submission in submissions:
        member = member_from_project_submission(
            submission,
            metadata,
            deadline=deadline,
        )
        if member is not None:
            members.append(member)
    return members


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


def homework_reminder_event(config, spec, homework):
    metadata = reminder_metadata(
        homework.course,
        item_slug_key="homework_slug",
        item_slug=homework.slug,
        item_id_key="homework_id",
        item_id=homework.pk,
        reminder_key="24h",
        deadline_kind=spec.deadline_kind,
    )
    members = reminder_members_from_enrollments(
        pending_homework_enrollments(homework),
        metadata,
        homework.due_date,
    )
    if not members:
        return None
    return build_reminder_event(
        config,
        spec,
        course=homework.course,
        item_id=homework.pk,
        item_slug=homework.slug,
        item_title=homework.title,
        reminder_key="24h",
        deadline=homework.due_date,
        members=members,
        metadata=metadata,
        context_extra=homework_deadline_context(homework),
    )


def project_submission_reminder_event(config, spec, project, reminder_key):
    metadata = reminder_metadata(
        project.course,
        item_slug_key="project_slug",
        item_slug=project.slug,
        item_id_key="project_id",
        item_id=project.pk,
        reminder_key=reminder_key,
        deadline_kind=spec.deadline_kind,
    )
    members = reminder_members_from_enrollments(
        pending_project_submission_enrollments(project),
        metadata,
        project.submission_due_date,
    )
    if not members:
        return None
    return build_reminder_event(
        config,
        spec,
        course=project.course,
        item_id=project.pk,
        item_slug=project.slug,
        item_title=project.title,
        reminder_key=reminder_key,
        deadline=project.submission_due_date,
        members=members,
        metadata=metadata,
        context_extra=project_submission_deadline_context(project),
    )


def peer_review_reminder_event(config, spec, project):
    metadata = reminder_metadata(
        project.course,
        item_slug_key="project_slug",
        item_slug=project.slug,
        item_id_key="project_id",
        item_id=project.pk,
        reminder_key="24h",
        deadline_kind=spec.deadline_kind,
    )
    members = reminder_members_from_submissions(
        pending_peer_review_submissions(project),
        metadata,
        project.peer_review_due_date,
    )
    if not members:
        return None
    return build_reminder_event(
        config,
        spec,
        course=project.course,
        item_id=project.pk,
        item_slug=project.slug,
        item_title=project.title,
        reminder_key="24h",
        deadline=project.peer_review_due_date,
        members=members,
        metadata=metadata,
        context_extra=peer_review_deadline_context(project),
    )


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
    return list(events.values())


def reminder_event_member_count(events):
    total_members = 0
    for event in events:
        total_members += len(event.members)
    return total_members


def require_datamailer_config():
    config = DatamailerConfig.from_settings()
    if config is None:
        raise CommandError(
            "Datamailer is not configured. Set DATAMAILER_URL, "
            "DATAMAILER_API_KEY, DATAMAILER_CLIENT, and DATAMAILER_AUDIENCE."
        )
    return config


def event_send_suffix(response):
    if not response:
        return ""
    enqueued_count = response.get("enqueued_count")
    if enqueued_count is None:
        return ""
    return f"; enqueued={enqueued_count}"


def send_reminder_event(client, config, event):
    payload = transient_recipient_list_send_payload(event)
    try:
        response = client.send_transient_recipient_list_transactional(
            payload,
        )
    except requests.RequestException as exc:
        record_datamailer_send_audit(
            send_type=DatamailerSendAuditType.TRANSIENT_RECIPIENT_LIST,
            payload=payload,
            list_key=event.list_key,
            error=str(exc),
        )
        if config.strict:
            raise
        raise CommandError(
            f"Datamailer deadline reminder failed for "
            f"{event.list_key}: {exc}"
        ) from exc

    record_datamailer_send_audit(
        send_type=DatamailerSendAuditType.TRANSIENT_RECIPIENT_LIST,
        payload=payload,
        list_key=event.list_key,
        response=response,
    )
    return response


class Command(BaseCommand):
    help = "Send Datamailer deadline reminders with transient recipient lists."

    def add_arguments(self, parser):
        parser.add_argument(
            "--course-slug",
            default="",
            help="Limit reminders to one course cohort slug.",
        )
        parser.add_argument(
            "--now",
            default="",
            help="Override current time with an ISO-8601 datetime.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print planned reminder sends without calling Datamailer.",
        )

    def handle(self, *args, **options):
        config = require_datamailer_config()
        now = aware_now(options["now"])
        events = build_reminder_events(
            config,
            now,
            course_slug=options["course_slug"],
        )
        total_members = reminder_event_member_count(events)
        self.stdout.write(
            f"Prepared {len(events)} reminder event(s), "
            f"{total_members} member(s)."
        )

        if options["dry_run"]:
            for event in events:
                self.stdout.write(
                    f"{event.list_key}: {len(event.members)} member(s)"
                )
            return

        client = DatamailerClient(config)
        for event in events:
            response = send_reminder_event(client, config, event)
            self.stdout.write(
                f"Sent {event.list_key}: "
                f"{len(event.members)} member(s)"
                f"{event_send_suffix(response)}"
            )
