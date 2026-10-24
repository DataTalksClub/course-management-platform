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
        "name": registration.name,
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
        if registration.status != "pending" or not (
            registration.course
            and registration.course.requires_registration_approval
        ):
            return
        template = "application-pending-operator"
        recipients = operator_recipients()
        sequence = 0
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


def send_notification(notification):
    payload = {
        "client": settings.RELAY_CLIENT,
        "email": notification.recipient,
        "template_key": notification.template_key,
        "category_tag": "transactional",
        "idempotency_key": f"cmp-application:{notification.idempotency_key}",
        "context": notification.context,
        "metadata": {"source": "cmp-application-notifications"},
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
    return str(message.get("id", ""))


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
        error = type(exc).__name__
        logger.error("Relay application notification failed id=%s error=%s", pk, error)
        ApplicationNotification.objects.filter(pk=pk).update(
            status="failed", last_error=error,
            next_attempt_at=timezone.now() + timedelta(minutes=5),
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
