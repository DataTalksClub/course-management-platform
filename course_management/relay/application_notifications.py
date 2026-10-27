"""Application lifecycle notifications through the Relay transactional API."""

import logging
from datetime import timedelta
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Max, Q
from django.urls import reverse
from django.utils import timezone

from course_management.observability import record_event
from course_management.worker_lock import worker_lock
from courses.models.application_notification import ApplicationNotification

logger = logging.getLogger(__name__)
DEFAULT_OPERATOR = "alexey@datatalks.club"
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


def operator_recipients():
    configured = getattr(settings, "APPLICATION_NOTIFICATION_OPERATORS", [])
    if isinstance(configured, str):
        configured = configured.split(",")
    recipients = {DEFAULT_OPERATOR}
    for raw in configured:
        email = raw.strip().lower()
        if email:
            validate_email(email)
            recipients.add(email)
    return sorted(recipients)


def notification_context(registration):
    from django.contrib.sites.models import Site

    domain = Site.objects.get_current().domain
    base = getattr(settings, "SITE_URL", "") or f"https://{domain}"
    base = base.rstrip("/")
    course = registration.course
    return {
        "name": (registration.name or "").strip() or "Applicant",
        "applicant_email": registration.email_normalized,
        "campaign_title": registration.campaign.title,
        "course_title": course.title if course else registration.campaign.title,
        "course_url": base + (
            reverse("course", kwargs={"course_slug": course.slug})
            if course else reverse("registration_campaign", kwargs={
                "campaign_slug": registration.campaign.slug,
            })
        ),
        "review_url": base + reverse(
            "cadmin_campaign_registrations",
            kwargs={"campaign_slug": registration.campaign.slug},
        ) + "?status=pending",
    }


def queue_application_notifications(registration, previous_status):
    created = previous_status is None
    if created:
        # Per-registration operator emails are disabled: operators receive
        # one daily registration digest instead (see registration_digest).
        # Registrant-facing decision mail below is unchanged.
        return
    elif registration.status != previous_status and registration.status in {
        "approved", "rejected",
    }:
        template = f"application-{registration.status}"
        recipients = [registration.email_normalized]
        latest = registration.application_notifications.aggregate(
            sequence=Max("decision_sequence"),
        )["sequence"] or 0
        sequence = latest + 1
    else:
        return
    context = notification_context(registration)
    for recipient in recipients:
        ApplicationNotification.objects.get_or_create(
            registration=registration,
            decision_sequence=sequence,
            recipient=recipient,
            defaults={"template_key": template, "context": context},
        )


def relay_request(method, path, payload):
    base = getattr(settings, "RELAY_URL", "").rstrip("/")
    parsed = urlparse(base)
    if not (
        parsed.scheme in {"http", "https"} and parsed.netloc
        and getattr(settings, "RELAY_API_KEY", "")
        and getattr(settings, "RELAY_CLIENT", "")
    ):
        raise ValueError("relay_config_missing_or_invalid")
    response = requests.request(
        method, base + path,
        headers={"Authorization": f"Bearer {settings.RELAY_API_KEY}"},
        json=payload,
        timeout=getattr(settings, "RELAY_TIMEOUT_SECONDS", 60),
    )
    response.raise_for_status()
    result = response.json()
    if not isinstance(result, dict):
        raise ValueError("relay_invalid_response")
    return result


def send_transactional_message(
    template_key, recipient, context, idempotency_key,
    source="cmp-application-notifications",
):
    payload = {
        "client": settings.RELAY_CLIENT,
        "audience": settings.RELAY_AUDIENCE,
        "email": recipient,
        "template_key": template_key,
        "category_tag": "transactional",
        "idempotency_key": idempotency_key,
        "context": context,
        "metadata": {"source": source},
    }
    if getattr(settings, "RELAY_FROM_EMAIL", ""):
        payload["from_email"] = settings.RELAY_FROM_EMAIL
    if getattr(settings, "RELAY_TRANSACTIONAL_DRY_RUN", False):
        payload["dry_run"] = True
    result = relay_request("POST", "/api/transactional/send", payload)
    message = result.get("message") or {}
    if not isinstance(message, dict):
        raise ValueError("relay_invalid_message")
    if message.get("status") in {"failed", "skipped", "cancelled"}:
        raise ValueError("relay_message_not_accepted")
    dry_run_accepted = payload.get("dry_run") and result.get("would_deliver") is True
    if not message.get("id") and not dry_run_accepted:
        raise ValueError("relay_acknowledgement_missing")
    return str(message.get("id") or "")


def send_notification(notification):
    return send_transactional_message(
        notification.template_key,
        notification.recipient,
        notification.context,
        f"cmp-application:{notification.idempotency_key}",
    )


def process_application_notifications(limit=100):
    now = timezone.now()
    lease_expired = now - timedelta(minutes=5)
    eligible = Q(
        status__in=["pending", "failed"], next_attempt_at__lte=now,
    ) | Q(status="processing", last_attempt_at__lt=lease_expired)
    ids = list(ApplicationNotification.objects.filter(eligible).order_by(
        "created_at", "pk",
    ).values_list("pk", flat=True)[:limit])
    for pk in ids:
        with worker_lock(f"application-notification:{pk}") as acquired:
            if acquired:
                dispatch_notification(pk, now, lease_expired)
    return len(ids)


def dispatch_notification(pk, now, lease_expired):
    with transaction.atomic():
        notification = ApplicationNotification.objects.select_for_update().get(pk=pk)
        if notification.status == "sent" or (
            notification.status == "processing"
            and notification.last_attempt_at
            and notification.last_attempt_at >= lease_expired
        ) or notification.next_attempt_at > now:
            return
        notification.status = "processing"
        notification.attempt_count += 1
        notification.last_attempt_at = now
        notification.save()
    try:
        message_id = send_notification(notification)
    except (requests.RequestException, ValueError, ValidationError) as exc:
        # Never persist response bodies, credentials or recipient data in
        # logs/alerts. The failed row retains the identity for safe retry.
        # Permanent Relay 4xx (e.g. unknown template_key) backs off 24h to
        # avoid hot retry loops; transient errors retry in 5min.
        error = type(exc).__name__
        logger.error("Relay application notification failed id=%s error=%s", pk, error)
        if is_permanent_relay_error(exc):
            delay = PERMANENT_BACKOFF
        else:
            delay = RETRYABLE_BACKOFF
        ApplicationNotification.objects.filter(pk=pk).update(
            status="failed", last_error=error,
            next_attempt_at=timezone.now() + delay,
            updated_at=timezone.now(),
        )
        record_event("datamailer.health_warning", properties={
            "source": "application-notifications", "notification_id": pk,
            "status": "failed", "error": error,
        })
    else:
        ApplicationNotification.objects.filter(pk=pk).update(
            status="sent", relay_message_id=message_id, last_error="",
            updated_at=timezone.now(),
        )
