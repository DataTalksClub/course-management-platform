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
)
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


def recipient_list_payload(config, event):
    return {
        "audience": config.audience,
        "client": config.client,
        "list": {
            "type": "deadline_reminders",
            "name": event.list_name,
            "metadata": event.list_metadata,
        },
        "members": event.members,
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


def homework_events(config, now, course_slug):
    events = []
    reminder_start, reminder_end = utc_day_window(now, days_ahead=1)
    queryset = Homework.objects.select_related("course").filter(
        state=HomeworkState.OPEN.value,
        due_date__gte=reminder_start,
        due_date__lt=reminder_end,
    )
    if course_slug:
        queryset = queryset.filter(course__slug=course_slug)

    for homework in queryset.order_by("due_date", "pk"):
        submitted_student_ids = Submission.objects.filter(
            homework=homework
        ).values("student_id")
        enrollments = (
            Enrollment.objects.filter(
                course=homework.course,
                student__email_deadline_reminders=True,
            )
            .exclude(student_id__in=submitted_student_ids)
            .select_related("student", "course")
            .order_by("pk")
        )
        metadata = {
            "course_slug": homework.course.slug,
            "homework_slug": homework.slug,
            "homework_id": homework.pk,
            "reminder_key": "24h",
            "deadline_kind": "homework",
        }
        members = [
            member
            for enrollment in enrollments
            if (
                member := member_from_enrollment(
                    enrollment,
                    metadata,
                    deadline=homework.due_date,
                )
            )
            is not None
        ]
        if not members:
            continue

        action_url = public_url(
            reverse(
                "homework",
                kwargs={
                    "course_slug": homework.course.slug,
                    "homework_slug": homework.slug,
                },
            )
        )
        context = base_context(
            homework.course,
            reminder_key="24h",
            item_type="homework",
            item_slug=homework.slug,
            item_title=homework.title,
            deadline=homework.due_date,
            action_url=action_url,
        )
        context.update(
            {
                "homework_slug": homework.slug,
                "homework_title": homework.title,
                "homework_due_at": homework.due_date.isoformat(),
                "email_subject": (
                    f"Homework deadline soon: {homework.title}"
                ),
                "email_preview": (
                    "Your homework deadline is within 24 hours."
                ),
                "intro_text": (
                    f"{homework.title} in {homework.course.title} "
                    "is due within 24 hours."
                ),
                "action_text": f"Submit or update homework: {action_url}",
            }
        )
        event_key = f"deadline-reminder:homework:{homework.pk}:24h"
        events.append(
            ReminderEvent(
                key=event_key,
                list_key=(
                    "deadline-reminders:"
                    f"homework:{homework.course.slug}:{homework.slug}:24h"
                ),
                list_name=(
                    f"{homework.course.title} {homework.title} "
                    "24h deadline reminders"
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
        )
    return events


def project_submission_events(config, now, course_slug):
    events = []
    daily_start, daily_end = utc_day_window(now, days_ahead=1)
    weekly_start, weekly_end = utc_day_window(now, days_ahead=8)
    queryset = Project.objects.select_related("course").filter(
        state=ProjectState.COLLECTING_SUBMISSIONS.value,
    ).filter(
        Q(
            submission_due_date__gte=daily_start,
            submission_due_date__lt=daily_end,
        )
        | Q(
            submission_due_date__gte=weekly_start,
            submission_due_date__lt=weekly_end,
        )
    )
    if course_slug:
        queryset = queryset.filter(course__slug=course_slug)

    for project in queryset.order_by("submission_due_date", "pk"):
        if is_within_window(
            project.submission_due_date,
            daily_start,
            daily_end,
        ):
            reminder_key = "24h"
        else:
            reminder_key = "7d"

        submitted_student_ids = ProjectSubmission.objects.filter(
            project=project,
            volunteer_review_only=False,
        ).values("student_id")
        enrollments = (
            Enrollment.objects.filter(
                course=project.course,
                student__email_deadline_reminders=True,
            )
            .exclude(student_id__in=submitted_student_ids)
            .select_related("student", "course")
            .order_by("pk")
        )
        metadata = {
            "course_slug": project.course.slug,
            "project_slug": project.slug,
            "project_id": project.pk,
            "reminder_key": reminder_key,
            "deadline_kind": "project_submission",
        }
        members = [
            member
            for enrollment in enrollments
            if (
                member := member_from_enrollment(
                    enrollment,
                    metadata,
                    deadline=project.submission_due_date,
                )
            )
            is not None
        ]
        if not members:
            continue

        action_url = public_url(
            reverse(
                "project",
                kwargs={
                    "course_slug": project.course.slug,
                    "project_slug": project.slug,
                },
            )
        )
        context = base_context(
            project.course,
            reminder_key=reminder_key,
            item_type="project",
            item_slug=project.slug,
            item_title=project.title,
            deadline=project.submission_due_date,
            action_url=action_url,
        )
        context.update(
            {
                "project_slug": project.slug,
                "project_title": project.title,
                "project_due_at": project.submission_due_date.isoformat(),
                "email_subject": (
                    f"Project deadline soon: {project.title}"
                ),
                "email_preview": (
                    "Your project submission deadline is coming up."
                ),
                "intro_text": (
                    f"{project.title} in {project.course.title} "
                    "is due soon."
                ),
                "action_text": f"Submit or update project: {action_url}",
            }
        )
        event_key = (
            f"deadline-reminder:project:{project.pk}:{reminder_key}"
        )
        events.append(
            ReminderEvent(
                key=event_key,
                list_key=(
                    "deadline-reminders:"
                    "project-submission:"
                    f"{project.course.slug}:{project.slug}:{reminder_key}"
                ),
                list_name=(
                    f"{project.course.title} {project.title} "
                    f"{reminder_key} submission deadline reminders"
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
        )
    return events


def peer_review_events(config, now, course_slug):
    events = []
    reminder_start, reminder_end = utc_day_window(now, days_ahead=1)
    queryset = Project.objects.select_related("course").filter(
        state=ProjectState.PEER_REVIEWING.value,
        peer_review_due_date__gte=reminder_start,
        peer_review_due_date__lt=reminder_end,
    )
    if course_slug:
        queryset = queryset.filter(course__slug=course_slug)

    for project in queryset.order_by("peer_review_due_date", "pk"):
        reviewer_submissions = (
            ProjectSubmission.objects.filter(
                project=project,
                volunteer_review_only=False,
                student__email_deadline_reminders=True,
                reviewers__state=PeerReviewState.TO_REVIEW.value,
                reviewers__optional=False,
            )
            .filter(
                Q(student__email__isnull=False) & ~Q(student__email="")
            )
            .select_related("student", "enrollment", "project")
            .distinct()
            .order_by("pk")
        )
        metadata = {
            "course_slug": project.course.slug,
            "project_slug": project.slug,
            "project_id": project.pk,
            "reminder_key": "24h",
            "deadline_kind": "peer_review",
        }
        members = [
            member
            for submission in reviewer_submissions
            if (
                member := member_from_project_submission(
                    submission,
                    metadata,
                    deadline=project.peer_review_due_date,
                )
            )
            is not None
        ]
        if not members:
            continue

        action_url = public_url(
            reverse(
                "projects_eval",
                kwargs={
                    "course_slug": project.course.slug,
                    "project_slug": project.slug,
                },
            )
        )
        context = base_context(
            project.course,
            reminder_key="24h",
            item_type="peer_review",
            item_slug=project.slug,
            item_title=project.title,
            deadline=project.peer_review_due_date,
            action_url=action_url,
        )
        context.update(
            {
                "project_slug": project.slug,
                "project_title": project.title,
                "peer_review_due_at": (
                    project.peer_review_due_date.isoformat()
                ),
                "email_subject": (
                    f"Peer review deadline soon: {project.title}"
                ),
                "email_preview": (
                    "Your assigned peer reviews are due within 24 hours."
                ),
                "intro_text": (
                    f"Your assigned peer reviews for {project.title} "
                    f"in {project.course.title} are due within 24 hours."
                ),
                "action_text": f"Complete peer reviews: {action_url}",
            }
        )
        event_key = f"deadline-reminder:peer-review:{project.pk}:24h"
        events.append(
            ReminderEvent(
                key=event_key,
                list_key=(
                    "deadline-reminders:"
                    f"peer-review:{project.course.slug}:{project.slug}:24h"
                ),
                list_name=(
                    f"{project.course.title} {project.title} "
                    "24h peer review deadline reminders"
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
        )
    return events


def build_reminder_events(config, now, course_slug=""):
    events = OrderedDict()
    for event in (
        homework_events(config, now, course_slug)
        + project_submission_events(config, now, course_slug)
        + peer_review_events(config, now, course_slug)
    ):
        events[event.list_key] = event
    return list(events.values())


class Command(BaseCommand):
    help = "Reconcile and send Datamailer deadline reminders."

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
        config = DatamailerConfig.from_settings()
        if config is None:
            raise CommandError(
                "Datamailer is not configured. Set DATAMAILER_URL, "
                "DATAMAILER_API_KEY, DATAMAILER_CLIENT, and DATAMAILER_AUDIENCE."
            )

        now = aware_now(options["now"])
        events = build_reminder_events(
            config,
            now,
            course_slug=options["course_slug"],
        )
        total_members = sum(len(event.members) for event in events)
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
            payload = recipient_list_payload(config, event)
            try:
                client.reconcile_recipient_list_members(
                    event.list_key,
                    payload,
                )
                response = client.send_recipient_list_transactional(
                    event.list_key,
                    event.send_payload,
                )
            except requests.RequestException as exc:
                if config.strict:
                    raise
                raise CommandError(
                    f"Datamailer deadline reminder failed for "
                    f"{event.list_key}: {exc}"
                ) from exc

            enqueued_count = None
            if response:
                enqueued_count = response.get("enqueued_count")
            suffix = (
                f"; enqueued={enqueued_count}"
                if enqueued_count is not None
                else ""
            )
            self.stdout.write(
                f"Sent {event.list_key}: "
                f"{len(event.members)} member(s){suffix}"
            )
