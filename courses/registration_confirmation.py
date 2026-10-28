"""Double opt-in email confirmation for course registrations.

Flow: a new registration is stored with ``email_confirmed=False`` and a
secret token. The Relay confirmation email carries a confirm link with
that token; clicking it marks the registration confirmed. Tokens expire
after ``EMAIL_CONFIRMATION_TOKEN_TTL_DAYS``; resends are rate-limited by
a cooldown plus a per-registration cap.
"""

import logging
import secrets
import math
from datetime import timedelta

from django.core import signing
from django.db import transaction

from django.utils import timezone

logger = logging.getLogger(__name__)

EMAIL_CONFIRMATION_TOKEN_TTL_DAYS = 7
EMAIL_CONFIRMATION_RESEND_COOLDOWN_SECONDS = 60
EMAIL_CONFIRMATION_MAX_RESENDS = 10


def generate_confirmation_token():
    return secrets.token_urlsafe(32)


def confirmation_token_expired(registration, now=None):
    """True when the registration's token is older than the TTL."""
    now = now or timezone.now()
    sent_at = registration.email_confirmation_sent_at
    if sent_at is None:
        return True
    age = now - sent_at
    return age.days >= EMAIL_CONFIRMATION_TOKEN_TTL_DAYS


def issue_confirmation_token(registration, now=None):
    """Assign a fresh token and stamp the send time (call before send)."""
    now = now or timezone.now()
    if (
        registration.email_confirmation_sent_at is not None
        and now - registration.email_confirmation_sent_at
        >= timedelta(days=1)
    ):
        registration.email_confirmation_resend_count = 0
    registration.email_confirmation_token = (
        generate_confirmation_token()
    )
    registration.email_confirmation_sent_at = now
    registration.email_confirmation_resend_count = (
        registration.email_confirmation_resend_count or 0
    ) + 1
    registration.save(
        update_fields=[
            "email_confirmation_token",
            "email_confirmation_sent_at",
            "email_confirmation_resend_count",
        ]
    )
    return registration


def mark_registration_confirmed(registration, now=None):
    """Mark a registration confirmed; idempotent."""
    now = now or timezone.now()
    if registration.email_confirmed:
        return False
    registration.email_confirmed = True
    registration.email_confirmation_confirmed_at = now
    registration.save(
        update_fields=[
            "email_confirmed",
            "email_confirmation_confirmed_at",
        ]
    )
    from courses.cross_sell import confirm_cross_sell_registrations

    confirm_cross_sell_registrations(registration, now=now)
    return True


def resend_cooldown_remaining_seconds(registration, now=None):
    now = now or timezone.now()
    sent_at = registration.email_confirmation_sent_at
    if sent_at is None:
        return 0
    elapsed = (now - sent_at).total_seconds()
    remaining = EMAIL_CONFIRMATION_RESEND_COOLDOWN_SECONDS - elapsed
    return max(0, math.ceil(remaining))


def resend_allowed(registration, now=None):
    """(allowed, reason) rate-limit check for confirmation resends."""
    if registration.email_confirmed:
        return False, "already_confirmed"
    now = now or timezone.now()
    recent = (
        registration.email_confirmation_sent_at is not None
        and now - registration.email_confirmation_sent_at
        < timedelta(days=1)
    )
    if recent and (
        registration.email_confirmation_resend_count or 0
    ) >= (EMAIL_CONFIRMATION_MAX_RESENDS):
        return False, "too_many_resends"
    remaining = resend_cooldown_remaining_seconds(registration, now=now)
    if remaining > 0:
        return False, f"cooldown_{remaining}s"
    return True, ""


@transaction.atomic
def confirm_registration_by_token(model_class, token, now=None):
    """Confirm a registration by token.

    Returns (registration_or_None, outcome) where outcome is one of
    "confirmed", "already_confirmed", "expired", "invalid".
    """
    now = now or timezone.now()
    token = (token or "").strip()
    if not token:
        return None, "invalid"
    try:
        registration = (
            model_class.objects.select_for_update(of=("self",))
            .select_related("campaign", "course")
            .get(email_confirmation_token=token)
        )
    except model_class.DoesNotExist:
        return None, "invalid"
    if registration.email_confirmed:
        return registration, "already_confirmed"
    if confirmation_token_expired(registration, now=now):
        return registration, "expired"
    mark_registration_confirmed(registration, now=now)
    return registration, "confirmed"


MANAGEMENT_TOKEN_SALT = "registration-email-management"


def management_token(registration):
    """Browser capability to resend/correct, never to confirm ownership."""
    return signing.dumps(
        [registration.pk, registration.email_normalized],
        salt=MANAGEMENT_TOKEN_SALT,
    )


def managed_registration(model_class, token):
    try:
        pk, email = signing.loads(
            token, salt=MANAGEMENT_TOKEN_SALT, max_age=7 * 24 * 60 * 60
        )
    except (signing.BadSignature, ValueError, TypeError):
        return None
    return (
        model_class.objects.select_for_update(of=("self",))
        .select_related("campaign", "course")
        .filter(pk=pk, email_normalized=email)
        .first()
    )
