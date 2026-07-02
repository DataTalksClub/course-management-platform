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
        response = client.recipient_lists.send_transient_recipient_list_transactional(
            payload,
        )
    except requests.RequestException as exc:
        error = str(exc)
        record_failed_reminder_send(event, payload, error)
        if config.strict:
            raise
        raise CommandError(
            f"Datamailer deadline reminder failed for "
            f"{event.list_key}: {exc}"
        ) from exc

    record_successful_reminder_send(event, payload, response)
    return response


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
        self.send_events(client, config, events)

    def write_dry_run_events(self, events):
        for event in events:
            self.stdout.write(
                f"{event.list_key}: {len(event.members)} member(s)"
            )

    def send_events(self, client, config, events):
        for event in events:
            response = send_reminder_event(client, config, event)
            suffix = event_send_suffix(response)
            message = (
                f"Sent {event.list_key}: "
                f"{len(event.members)} member(s)"
                f"{suffix}"
            )
            self.stdout.write(message)
