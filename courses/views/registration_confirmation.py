"""Double opt-in confirmation endpoints for course registrations.

- ``registration_confirm_view`` (GET ``register/confirm/<token>/``):
  marks the registration confirmed; idempotent; expired/invalid tokens
  render a page with a resend option.
- ``registration_confirmation_resend_view`` (POST): rate-limited resend.
- ``registration_confirmation_fix_email_view`` (POST): correct the
  address ("wrong email? fix it") and send a new confirmation.
"""

import logging

from django.contrib import messages
from django.db import transaction
from django.forms import EmailField
from django.forms import ValidationError as FormValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from course_management.relay.registration import (
    sync_registration_to_relay,
)
from course_management.relay.notifications import (
    send_registration_confirmation_email,
)
from course_management.observability import record_event
from courses.email_validation import (
    email_domain_has_mx,
    suggest_email_correction,
)
from courses.models.course import CourseRegistration
from courses.registration_confirmation import (
    confirm_registration_by_token,
    issue_confirmation_token,
    resend_allowed,
    managed_registration,
)
from courses.views.registration_form import (
    normalized_registration_email,
    registration_email_taken,
)

logger = logging.getLogger(__name__)


def _queue_confirmation_send(request, registration, *, immediate=False):
    if immediate:
        sync_registration_to_relay(registration)
        return send_registration_confirmation_email(registration)
    sync_callback = lambda: sync_registration_to_relay(registration)
    email_callback = lambda: send_registration_confirmation_email(
        registration
    )
    transaction.on_commit(sync_callback)
    transaction.on_commit(email_callback)
    return True


def _safe_next_url(request: HttpRequest) -> str:
    candidate = (request.POST.get("next") or "").strip()
    if not candidate:
        return ""
    if url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return ""


def _rate_limit_message(reason: str) -> str:
    if reason == "too_many_resends":
        return (
            "Too many confirmation emails were requested for this "
            "registration. Please try again after 24 hours."
        )
    if reason.startswith("cooldown_") and reason.endswith("s"):
        seconds = reason.removeprefix("cooldown_").removesuffix("s")
        return (
            "Please wait a minute before requesting another confirmation "
            f"email (try again in {seconds}s)."
        )
    return (
        "Please wait a minute before requesting another confirmation email."
    )


@never_cache
@require_GET
def registration_confirm_view(request, token):
    registration, outcome = confirm_registration_by_token(
        CourseRegistration, token
    )
    if registration is not None:
        record_event(
            "registration.confirmed",
            request=request,
            user=getattr(request, "user", None),
            properties={
                "campaign_slug": registration.campaign.slug,
                "registration_id": registration.id,
                "outcome": outcome,
                "path": "/register/confirm/[redacted]/",
            },
        )
        campaign = registration.campaign
    else:
        campaign = None
    from courses.models.course import RegistrationCampaign

    context = {
        "campaigns": RegistrationCampaign.objects.filter(
            is_active=True
        ),
        "registration": registration,
        "campaign": campaign,
        "outcome": outcome,
    }
    response = render(
        request, "courses/registration_confirm.html", context
    )
    response["Referrer-Policy"] = "no-referrer"
    return response


def registration_confirmation_resend_view(
    request: HttpRequest,
) -> HttpResponse:
    if request.method != "POST":
        return render(
            request,
            "courses/registration_resend_status.html",
            {
                "sent": False,
                "error": "Use the resend button to request an email.",
            },
            status=405,
        )
    next_url = _safe_next_url(request)
    token = (request.POST.get("token") or "").strip()
    if not token and request.POST.get("email"):
        with transaction.atomic():
            return _public_resend(request)

    with transaction.atomic():
        registration = managed_registration(CourseRegistration, token)
        if registration is None or not token:
            error_message = (
                "That confirmation link is invalid. Please register again."
            )
            if next_url:
                messages.error(request, error_message)
                return redirect(next_url)
            return render(
                request,
                "courses/registration_resend_status.html",
                {
                    "sent": False,
                    "error": error_message,
                    "registration": None,
                    "campaign": None,
                },
            )
        campaign = registration.campaign
        if registration.email_confirmed:
            if next_url:
                messages.success(
                    request,
                    f"{registration.email} is already confirmed. "
                    f"Your registration for {campaign.title} is complete.",
                )
                return redirect(next_url)
            return render(
                request,
                "courses/registration_resend_status.html",
                {
                    "sent": False,
                    "already_confirmed": True,
                    "registration": registration,
                    "campaign": campaign,
                },
            )
        allowed, reason = resend_allowed(registration)
        if not allowed:
            error_message = _rate_limit_message(reason)
            if next_url:
                messages.warning(request, error_message)
                return redirect(next_url)
            return render(
                request,
                "courses/registration_resend_status.html",
                {
                    "sent": False,
                    "rate_limited": True,
                    "reason": reason,
                    "error": error_message,
                    "registration": registration,
                    "campaign": campaign,
                },
                status=429 if reason != "already_confirmed" else 200,
            )
        issue_confirmation_token(registration)

    send_result = _queue_confirmation_send(
        request, registration, immediate=True
    )
    if send_result is None:
        error_message = (
            f"Could not send the confirmation email to {registration.email} "
            "right now. Please try again shortly."
        )
        if next_url:
            messages.error(request, error_message)
            return redirect(next_url)
        return render(
            request,
            "courses/registration_resend_status.html",
            {
                "sent": False,
                "send_failed": True,
                "error": error_message,
                "registration": registration,
                "campaign": campaign,
            },
        )

    record_event(
        "registration.confirmation_resent",
        request=request,
        user=getattr(request, "user", None),
        properties={
            "campaign_slug": campaign.slug,
            "registration_id": registration.id,
        },
    )
    if next_url:
        messages.success(
            request,
            f"Confirmation email sent to {registration.email}. "
            "Check your inbox and click the confirmation link to complete "
            "your registration.",
        )
        return redirect(next_url)
    return render(
        request,
        "courses/registration_resend_status.html",
        {
            "sent": True,
            "registration": registration,
            "campaign": campaign,
        },
    )


def validate_fixed_confirmation_email(campaign, registration, email):
    """Returns (normalized, error_message). Empty error means valid."""
    email_field = EmailField()
    try:
        email_field.clean(email)
    except FormValidationError:
        return "", "Enter a valid email address."
    normalized = normalized_registration_email(email)
    suggestion = suggest_email_correction(normalized)
    if suggestion and suggestion.lower() != normalized:
        return "", f"Did you mean {suggestion}?"
    mx_result = email_domain_has_mx(normalized)
    if mx_result is False:
        return "", (
            "That email domain does not accept mail. "
            "Please check the address."
        )
    if registration_email_taken(campaign, normalized):
        if normalized != registration.email_normalized:
            return (
                "",
                "That address is already registered for this course.",
            )
    return normalized, ""


@transaction.atomic
def registration_confirmation_fix_email_view(
    request: HttpRequest,
) -> HttpResponse:
    if request.method != "POST":
        return render(
            request,
            "courses/registration_fix_email_status.html",
            {
                "updated": False,
                "error": "Use the fix-email form to update.",
            },
            status=405,
        )
    token = (request.POST.get("token") or "").strip()
    new_email = (request.POST.get("email") or "").strip()
    registration = managed_registration(CourseRegistration, token)
    if registration is None or not token:
        return render(
            request,
            "courses/registration_fix_email_status.html",
            {
                "updated": False,
                "error": (
                    "That confirmation link is invalid. "
                    "Please register again."
                ),
                "registration": None,
                "campaign": None,
            },
        )
    campaign = registration.campaign
    if registration.email_confirmed:
        return render(
            request,
            "courses/registration_fix_email_status.html",
            {
                "updated": False,
                "already_confirmed": True,
                "registration": registration,
                "campaign": campaign,
            },
        )
    allowed, reason = resend_allowed(registration)
    if not allowed:
        return render(
            request,
            "courses/registration_fix_email_status.html",
            {
                "registration": registration,
                "campaign": campaign,
                "error": "Please wait a minute before trying again."
                if reason.startswith("cooldown")
                else "Too many confirmation requests. Please try again after 24 hours.",
            },
            status=429,
        )
    normalized, error = validate_fixed_confirmation_email(
        campaign, registration, new_email
    )
    if error:
        return render(
            request,
            "courses/registration_fix_email_status.html",
            {
                "updated": False,
                "error": error,
                "registration": registration,
                "campaign": campaign,
            },
        )
    registration.email = new_email.strip()
    registration.email_normalized = normalized
    registration.save(
        update_fields=[
            "email",
            "email_normalized",
        ]
    )
    # Unconfirmed cross-sell copies were made for the wrong address; drop
    # them so they do not linger. The success page offers them again.
    registration.cross_sell_registrations.filter(
        email_confirmed=False
    ).delete()
    issue_confirmation_token(registration)
    _queue_confirmation_send(request, registration)
    record_event(
        "registration.confirmation_email_fixed",
        request=request,
        user=getattr(request, "user", None),
        properties={
            "campaign_slug": campaign.slug,
            "registration_id": registration.id,
        },
    )
    return render(
        request,
        "courses/registration_fix_email_status.html",
        {
            "updated": True,
            "registration": registration,
            "campaign": campaign,
        },
    )


def _public_resend(request):
    """Recovery for a lost/invalid link; disclose no registration identity."""
    email = normalized_registration_email(request.POST.get("email", ""))
    campaign_slug = request.POST.get("campaign_slug", "").strip()
    registration = (
        CourseRegistration.objects.select_for_update()
        .filter(email_normalized=email, campaign__slug=campaign_slug)
        .first()
    )
    if registration is not None and resend_allowed(registration)[0]:
        issue_confirmation_token(registration)
        _queue_confirmation_send(request, registration)
    return render(
        request,
        "courses/registration_resend_status.html",
        {"recovery_requested": True},
    )
