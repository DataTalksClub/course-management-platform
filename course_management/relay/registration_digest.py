"""Daily registration digest email to operators through Relay.

Replaces the per-registration ``application-pending-operator`` emails: new
registrations no longer notify operators individually. Instead the minutely
``process_datamailer_outbox`` schedule sends one digest per Europe/Berlin
day, covering the last 24h of registrations grouped by course. When the
window holds zero registrations no email is sent (a ``skipped_empty`` row
records the decision). Registrant-facing mail (confirmation,
application-approved/rejected) is unchanged.
"""

import html
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from course_management.observability import record_event
from course_management.worker_lock import worker_lock
from courses.models.registration_digest import RegistrationDigestSend

from .application_notifications import (
    operator_recipients,
    send_transactional_message,
)

logger = logging.getLogger(__name__)

DIGEST_TEMPLATE = "registration-digest-operator"
DIGEST_TIMEZONE = ZoneInfo("Europe/Berlin")
DIGEST_SEND_HOUR = 9
DIGEST_WINDOW = timedelta(hours=24)
DIGEST_JOB = "digest"

REASONS = ("sent", "empty", "already-sent", "locked", "failed")


@dataclass
class DigestResult:
    sent: bool
    reason: str
    date: object = None
    total_count: int = 0
    relay_message_ids: list = field(default_factory=list)


def digest_moment(now=None):
    return now if now is not None else timezone.now()


def digest_day(now=None):
    return digest_moment(now).astimezone(DIGEST_TIMEZONE).date()


def digest_due(now=None):
    """True once per Europe/Berlin day after 09:00 until sent (or skipped)."""
    moment = digest_moment(now)
    berlin = moment.astimezone(DIGEST_TIMEZONE)
    if berlin.hour < DIGEST_SEND_HOUR:
        return False
    return not RegistrationDigestSend.objects.filter(
        date=berlin.date(),
    ).exists()


def digest_idempotency_key(day, recipient):
    # Stable per day and recipient so restarts and rolling overlap never
    # double-send even if Relay receives the request twice. The recipient
    # address is already part of the Relay payload, so the key adds no new
    # PII exposure; keys never appear in logs.
    return f"cmp-registration-digest:{day.isoformat()}:{recipient}"


def collect_digest_registrations(window_start, window_end):
    from courses.models.course import CourseRegistration
    return list(
        CourseRegistration.objects.filter(
            created_at__gte=window_start,
            created_at__lt=window_end,
        ).select_related("course", "campaign").order_by("created_at", "pk")
    )


def digest_review_url(registration):
    from django.contrib.sites.models import Site

    domain = Site.objects.get_current().domain
    base = getattr(settings, "SITE_URL", "") or f"https://{domain}"
    return base.rstrip("/") + reverse(
        "cadmin_campaign_registrations",
        kwargs={"campaign_slug": registration.campaign.slug},
    ) + "?status=pending"


def group_digest_registrations(registrations):
    groups = []
    by_key = {}
    for registration in registrations:
        course = registration.course
        if course is not None:
            key = ("course", course.pk)
            title = course.title
        else:
            key = ("campaign", registration.campaign_id)
            title = registration.campaign.title
        group = by_key.get(key)
        if group is None:
            group = {
                "title": title,
                "review_url": digest_review_url(registration),
                "members": [],
            }
            by_key[key] = group
            groups.append(group)
        group["members"].append({
            "name": (registration.name or "").strip() or "Applicant",
            "email": registration.email_normalized,
            "confirmed": bool(registration.email_confirmed),
        })
    return groups


def render_digest_summary(groups):
    lines = []
    for group in groups:
        members = group["members"]
        confirmed = sum(1 for member in members if member["confirmed"])
        unconfirmed = len(members) - confirmed
        lines.append(
            f"{group['title']} — {len(members)} new "
            f"({confirmed} confirmed, {unconfirmed} unconfirmed)"
        )
        lines.append(f"Review pending: {group['review_url']}")
        for member in group["members"]:
            state = "confirmed" if member["confirmed"] else "unconfirmed"
            lines.append(
                f"- {member['name']} <{member['email']}> — {state}"
            )
        lines.append("")
    return "\n".join(lines).rstrip("\n")


def render_digest_summary_html(groups):
    return html.escape(render_digest_summary(groups))


def build_digest_context(registrations, day):
    groups = group_digest_registrations(registrations)
    total = len(registrations)
    confirmed = sum(1 for item in registrations if item.email_confirmed)
    return {
        "digest_date": day.isoformat(),
        "total_count": total,
        "confirmed_count": confirmed,
        "unconfirmed_count": total - confirmed,
        "course_count": len(groups),
        "summary": render_digest_summary(groups),
        "summary_html": render_digest_summary_html(groups),
    }


def mark_digest_job(started=False, succeeded=False, failed=False):
    from data.models import CmpJobState

    state, _ = CmpJobState.objects.get_or_create(job=DIGEST_JOB)
    now = timezone.now()
    updates = []
    if started:
        state.last_started_at = now
        updates.append("last_started_at")
    if succeeded:
        state.last_success_at = now
        updates.append("last_success_at")
    if failed:
        state.last_failed_at = now
        updates.append("last_failed_at")
    if updates:
        state.save(update_fields=updates)


def send_registration_digest(now=None, force=False):
    """Send today's digest once. Raises on transport failure; never double-sends.

    Without ``force``, any existing row for the day (sent or skipped_empty)
    is final. Relay sends run outside the database transaction; a crash
    between sending and recording retries with the same per-day,
    per-recipient idempotency keys, which Relay deduplicates.
    """
    moment = digest_moment(now)
    day = moment.astimezone(DIGEST_TIMEZONE).date()
    window_start = moment - DIGEST_WINDOW
    window_end = moment
    mark_digest_job(started=True)
    with worker_lock(f"registration-digest:{day}") as acquired:
        if not acquired:
            return DigestResult(sent=False, reason="locked", date=day)
        try:
            with transaction.atomic():
                existing = RegistrationDigestSend.objects.select_for_update().filter(
                    date=day,
                ).first()
                if existing is not None and not force:
                    mark_digest_job(succeeded=True)
                    return DigestResult(
                        sent=False, reason="already-sent", date=day,
                        total_count=existing.total_count,
                        relay_message_ids=list(existing.relay_message_ids or []),
                    )
                registrations = collect_digest_registrations(window_start, window_end)
                if not registrations:
                    RegistrationDigestSend.objects.update_or_create(
                        date=day,
                        defaults={
                            "status": RegistrationDigestSend.Status.SKIPPED_EMPTY,
                            "window_start": window_start,
                            "window_end": window_end,
                            "total_count": 0,
                            "confirmed_count": 0,
                            "unconfirmed_count": 0,
                            "course_count": 0,
                            "recipients": [],
                            "relay_message_ids": [],
                            "relay_idempotency_keys": [],
                        },
                    )
                    mark_digest_job(succeeded=True)
                    return DigestResult(sent=False, reason="empty", date=day)
            context = build_digest_context(registrations, day)
            recipients = operator_recipients()
            message_ids = []
            idempotency_keys = []
            for recipient in recipients:
                key = digest_idempotency_key(day, recipient)
                message_ids.append(send_transactional_message(
                    DIGEST_TEMPLATE, recipient, context, key,
                    source="cmp-registration-digest",
                ))
                idempotency_keys.append(key)
            with transaction.atomic():
                RegistrationDigestSend.objects.update_or_create(
                    date=day,
                    defaults={
                        "status": RegistrationDigestSend.Status.SENT,
                        "window_start": window_start,
                        "window_end": window_end,
                        "total_count": len(registrations),
                        "confirmed_count": sum(
                            1 for item in registrations if item.email_confirmed
                        ),
                        "unconfirmed_count": sum(
                            1 for item in registrations if not item.email_confirmed
                        ),
                        "course_count": context["course_count"],
                        "recipients": list(recipients),
                        "relay_message_ids": message_ids,
                        "relay_idempotency_keys": idempotency_keys,
                    },
                )
            mark_digest_job(succeeded=True)
            return DigestResult(
                sent=True, reason="sent", date=day,
                total_count=len(registrations),
                relay_message_ids=message_ids,
            )
        except Exception as exc:
            mark_digest_job(failed=True)
            # Never persist response bodies, credentials or recipient data.
            logger.error(
                "Registration digest send failed date=%s error=%s",
                day, type(exc).__name__,
            )
            record_event("datamailer.health_warning", properties={
                "source": "registration-digest",
                "date": day.isoformat(),
                "status": "failed",
                "error": type(exc).__name__,
            })
            raise


def maybe_send_scheduled_digest(now=None):
    """Best-effort daily digest hook for the minutely outbox schedule.

    Returns a DigestResult (or None when not due). Never raises: digest
    trouble must not block Datamailer outbox processing.
    """
    moment = digest_moment(now)
    try:
        if not digest_due(moment):
            return None
        return send_registration_digest(now=moment)
    except Exception as exc:
        logger.error(
            "Scheduled registration digest skipped error=%s",
            type(exc).__name__,
        )
        return DigestResult(
            sent=False, reason="failed",
            date=moment.astimezone(DIGEST_TIMEZONE).date(),
        )
