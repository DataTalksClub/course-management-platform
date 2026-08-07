import requests
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from course_management.datamailer.client import (
    DatamailerClient,
    DatamailerConfig,
)
from course_management.datamailer.sync.audit import (
    DatamailerSendAuditData,
    record_datamailer_send_audit,
)
from data.models import DatamailerSendAuditType
from courses.deadline_reminder_events import (
    build_reminder_events,
    reminder_event_member_count,
)
from courses.deadline_reminder_payloads import transient_recipient_list_send_payload


def aware_now(value: str):
    if not value:
        return timezone.now()

    parsed = parse_datetime(value)
    if parsed is None:
        raise CommandError("--now must be an ISO-8601 datetime.")
    if timezone.is_naive(parsed):
        current_timezone = timezone.get_current_timezone()
        parsed = timezone.make_aware(parsed, current_timezone)
    return parsed


def require_datamailer_config():
    config = DatamailerConfig.from_settings()
    if config is None:
        raise CommandError(
            "Datamailer is not configured. Set RELAY_URL, "
            "RELAY_API_KEY, RELAY_CLIENT, and RELAY_AUDIENCE."
        )
    return config


def event_send_suffix(response):
    if not response:
        return ""
    enqueued_count = response.get("enqueued_count")
    if enqueued_count is None:
        return ""
    return f"; enqueued={enqueued_count}"


def send_reminder_event(client, event):
    """Send one reminder event.

    Returns ``(response, error)``. A transport failure is returned rather
    than raised so one broken event cannot cancel the reminders queued
    behind it -- see ``Command.send_events``.
    """
    payload = transient_recipient_list_send_payload(event)
    try:
        response = client.recipient_lists.sends.send_to_transient_list(
            payload,
        )
    except requests.RequestException as exc:
        error = str(exc)
        record_failed_reminder_send(event, payload, error)
        return None, error

    record_successful_reminder_send(event, payload, response)
    return response, ""


def reminder_failure_summary(failures):
    lines = []
    for event, error in failures:
        lines.append(f"{event.list_key}: {error}")
    joined = "; ".join(lines)
    return f"Datamailer deadline reminders failed: {joined}"


def record_failed_reminder_send(event, payload, error):
    audit_data = DatamailerSendAuditData(
        send_type=DatamailerSendAuditType.TRANSIENT_RECIPIENT_LIST,
        payload=payload,
        list_key=event.list_key,
        error=error,
    )
    record_datamailer_send_audit(audit_data)


def record_successful_reminder_send(event, payload, response):
    audit_data = DatamailerSendAuditData(
        send_type=DatamailerSendAuditType.TRANSIENT_RECIPIENT_LIST,
        payload=payload,
        list_key=event.list_key,
        response=response,
    )
    record_datamailer_send_audit(audit_data)


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
            self.write_dry_run_events(events)
            return

        client = DatamailerClient(config)
        self.send_events(client, events)

    def write_dry_run_events(self, events):
        for event in events:
            self.stdout.write(
                f"{event.list_key}: {len(event.members)} member(s)"
            )

    def send_events(self, client, events):
        failures = []
        for event in events:
            response, error = send_reminder_event(client, event)
            if error:
                failures.append((event, error))
                self.stderr.write(
                    f"Failed {event.list_key}: "
                    f"{len(event.members)} member(s): {error}"
                )
                continue
            suffix = event_send_suffix(response)
            message = (
                f"Sent {event.list_key}: "
                f"{len(event.members)} member(s)"
                f"{suffix}"
            )
            self.stdout.write(message)

        if not failures:
            return

        self.stderr.write(
            f"{len(failures)} of {len(events)} reminder event(s) failed."
        )
        # Raise only after every event has been attempted, so the task
        # still exits non-zero and surfaces in CloudWatch.
        raise CommandError(reminder_failure_summary(failures))
