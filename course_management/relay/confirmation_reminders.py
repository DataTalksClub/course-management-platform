"""Two confirmation reminders and bounded cleanup for unconfirmed registrations."""
import logging
from datetime import timedelta
from zoneinfo import ZoneInfo

import requests
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from course_management.datamailer.payloads.registration_confirmations import registration_confirmation_urls
from course_management.worker_lock import worker_lock
from courses.models import CourseRegistration
from courses.registration_confirmation import EMAIL_CONFIRMATION_TOKEN_TTL_DAYS, generate_confirmation_token
from .application_notifications import send_transactional_message

logger = logging.getLogger(__name__)
REMINDERS = ((1, timedelta(hours=24)), (2, timedelta(hours=72)))
RETRYABLE_BACKOFF = timedelta(minutes=5)
PERMANENT_BACKOFF = timedelta(hours=24)


def is_permanent_relay_error(exc):
    """True for Relay 4xx that will never succeed on retry (except 429)."""
    if not isinstance(exc, requests.HTTPError):
        return False
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", 0) or 0
    if not status_code:
        return False
    if status_code == 429:
        return False
    return 400 <= status_code < 500


def backoff_for_error(exc):
    if is_permanent_relay_error(exc):
        return PERMANENT_BACKOFF
    return RETRYABLE_BACKOFF


def reminder_action(row, now):
    deadline = row.created_at + timedelta(days=7)
    if row.email_confirmed:
        return None
    if row.referred_by_id is not None:
        # Cross-sell copies confirm with their source registration and
        # are deleted with it (CASCADE); they never send reminders.
        return None
    next_attempt_at = getattr(row, "confirmation_reminder_next_attempt_at", None)
    if next_attempt_at is not None and next_attempt_at > now:
        return None
    if now > deadline and row.confirmation_reminder_2_sent_at is not None:
        return "delete"
    if row.confirmation_reminder_2_sent_at is not None:
        return None
    for number, delay in REMINDERS:
        if now >= row.created_at + delay and getattr(row, f"confirmation_reminder_{number}_sent_at") is None:
            return number
    return None


def reminder_context(row):
    deadline = (row.created_at + timedelta(days=7)).astimezone(ZoneInfo("Europe/Berlin"))
    return {
        "course_title": row.course.title if row.course else row.campaign.title,
        "confirmation_url": registration_confirmation_urls(row.campaign, row.course, row.email_confirmation_token)["confirmation_url"],
        "deadline": deadline.strftime("%Y-%m-%d %H:%M:%S %Z (Europe/Berlin)"),
    }


def process_one(pk, now):
    # Persist a replacement token before delivery, so an accepted Relay request
    # followed by a process crash retries with a still-valid identical link.
    with transaction.atomic():
        row = CourseRegistration.objects.select_for_update(of=("self",)).get(pk=pk)
        action = reminder_action(row, now)
        if isinstance(action, int):
            deadline = row.created_at + timedelta(days=7)
            sent = row.email_confirmation_sent_at
            if not row.email_confirmation_token or sent is None or sent + timedelta(days=EMAIL_CONFIRMATION_TOKEN_TTL_DAYS) < deadline or sent + timedelta(days=EMAIL_CONFIRMATION_TOKEN_TTL_DAYS) <= now:
                row.email_confirmation_token = generate_confirmation_token()
                row.email_confirmation_sent_at = now
                row.save(update_fields=["email_confirmation_token", "email_confirmation_sent_at"])
    with transaction.atomic():
        row = CourseRegistration.objects.select_for_update(of=("self",)).select_related("course", "campaign").get(pk=pk)
        action = reminder_action(row, now)
        if action == "delete":
            row.delete()
            return "deleted"
        if not isinstance(action, int):
            return None
        template_key = f"registration-confirmation-reminder-{action}"
        recipient = row.email_normalized
        context = reminder_context(row)
        idempotency_key = f"cmp-confirmation-reminder:{row.pk}:{action}"
    # Send outside the DB transaction: a failure must persist backoff even
    # though the send itself raises (saving inside the atomic block above
    # would roll back). Permanent Relay 4xx back off 24h, retryable 5min.
    try:
        send_transactional_message(
            template_key, recipient, context, idempotency_key,
            source="cmp-confirmation-reminders",
        )
    except Exception as exc:
        # Never persist response bodies or recipient data.
        delay = backoff_for_error(exc)
        CourseRegistration.objects.filter(pk=pk).update(
            confirmation_reminder_next_attempt_at=timezone.now() + delay,
        )
        raise
    with transaction.atomic():
        row = CourseRegistration.objects.select_for_update(of=("self",)).get(pk=pk)
        # Re-check under lock so a concurrent success cannot double-send.
        if reminder_action(row, now) != action:
            return None
        field = f"confirmation_reminder_{action}_sent_at"
        setattr(row, field, now)
        row.confirmation_reminder_next_attempt_at = None
        row.save(update_fields=[field, "confirmation_reminder_next_attempt_at"])
        return "reminded"


def process_confirmation_reminders(now=None, dry_run=False, limit=100):
    now = now or timezone.now()
    result = {"reminded": 0, "deleted": 0, "failed": 0}
    rows = CourseRegistration.objects.filter(
        email_confirmed=False, created_at__lte=now - timedelta(hours=24),
    ).filter(
        Q(confirmation_reminder_next_attempt_at__isnull=True)
        | Q(confirmation_reminder_next_attempt_at__lte=now),
    ).order_by("created_at", "pk")
    # Select only actionable rows so completed reminders cannot starve new ones.
    processed = 0
    for row in rows.iterator():
        action = reminder_action(row, now)
        if action is None:
            continue
        if processed >= limit:
            break
        processed += 1
        if dry_run:
            result["deleted" if action == "delete" else "reminded"] += 1
            continue
        with worker_lock(f"confirmation-reminder:{row.pk}") as acquired:
            if not acquired:
                continue
            try:
                outcome = process_one(row.pk, now)
                if outcome:
                    result[outcome] += 1
            except CourseRegistration.DoesNotExist:
                pass
            except Exception:
                # Do not log exception bodies, links, addresses or registrant data.
                result["failed"] += 1
    logger.info("Confirmation reminders dry_run=%s reminded=%s deleted=%s failed=%s", dry_run, result["reminded"], result["deleted"], result["failed"])
    return result
