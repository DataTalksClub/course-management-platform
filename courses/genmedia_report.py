"""Nightly Nebius report: approved-applicant CSV emailed after the run.

Mikhail (Nebius) gets the approved list; Alexey always gets a copy.
Rejected/excluded applicants are counted, never listed.
"""

import csv
import io
import logging
from zoneinfo import ZoneInfo

from django.utils import timezone

from courses.genmedia_policy import AUTO_APPROVAL_TIMEZONE

logger = logging.getLogger(__name__)

REPORT_TEMPLATE = "genmedia-nebius-approval-report"
REPORT_SOURCE = "genmedia-nebius-report"
NEBIUS_REPORT_RECIPIENTS = [
    "alexey.s.grigoriev@gmail.com",
    "mnrozhkov@nebius.com",
]


def send_transactional_message(recipient, payload):
    """Send one report email through the Relay transactional API.

    Kept as a module-level name so tests can patch
    ``courses.genmedia_report.send_transactional_message``.
    """
    from course_management.relay.application_notifications import (
        send_transactional_message as relay_send,
    )

    return relay_send(
        payload["template_key"],
        recipient,
        payload["context"],
        payload["idempotency_key"],
        source=REPORT_SOURCE,
    )


def report_idempotency_key(day, recipient):
    # Stable per day and recipient so restarts and rolling overlap never
    # double-send even if Relay receives the request twice.
    return f"cmp-genmedia-nebius-report:{day.isoformat()}:{recipient}"


def build_approved_csv(approved):
    """CSV of approved registrations (excluded applicants never listed)."""
    zone = ZoneInfo(AUTO_APPROVAL_TIMEZONE)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ("name", "email", "country", "ukraine_region", "approved_at")
    )
    for registration in approved:
        writer.writerow(
            (
                registration.name,
                registration.email_normalized,
                registration.country,
                registration.get_ukraine_region_display(),
                timezone.localtime(
                    registration.auto_approved_at, zone
                ).isoformat(),
            )
        )
    return buffer.getvalue()


def send_nebius_report(*, day, approved, excluded_count):
    """Email the approved CSV to Nebius + Alexey. No-op when nothing approved.

    Returns the list of Relay message ids (empty when nothing was sent).
    Never raises: report trouble must not fail the approval run.
    """
    approved = list(approved)
    if not approved:
        return []
    csv_text = build_approved_csv(approved)
    context = {
        "date_label": day.isoformat(),
        "approved_count": len(approved),
        "excluded_count": excluded_count,
        "csv_text": csv_text,
    }
    message_ids = []
    for recipient in NEBIUS_REPORT_RECIPIENTS:
        try:
            message_ids.append(
                send_transactional_message(
                    recipient,
                    {
                        "template_key": REPORT_TEMPLATE,
                        "context": context,
                        "idempotency_key": report_idempotency_key(
                            day, recipient
                        ),
                    },
                )
            )
        except Exception:
            logger.error(
                "Genmedia Nebius report send failed day=%s",
                day,
            )
    return message_ids
