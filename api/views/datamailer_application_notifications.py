from django.db.models import Q
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from accounts.auth import token_required
from api.safety import require_staff_token
from courses.models import ApplicationNotification, CourseRegistration

DEFAULT_LIMIT = 25
MAX_LIMIT = 200


@require_GET
@token_required
def datamailer_application_notifications_view(request):
    """List ApplicationNotification rows and registration diagnostics (staff only)."""
    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    qs = ApplicationNotification.objects.select_related(
        "registration",
        "registration__campaign",
        "registration__course",
    )

    registration_obj = None
    raw_reg_id = request.GET.get("registration_id")
    if raw_reg_id:
        try:
            reg_id = int(raw_reg_id)
        except (TypeError, ValueError):
            return JsonResponse(
                {"error": "invalid_registration_id"},
                status=400,
            )
        qs = qs.filter(registration_id=reg_id)
        registration_obj = (
            CourseRegistration.objects.select_related("campaign", "course")
            .filter(pk=reg_id)
            .first()
        )

    email = request.GET.get("email")
    if email:
        normalized = email.strip().lower()
        qs = qs.filter(
            Q(recipient__iexact=normalized)
            | Q(registration__email_normalized=normalized)
        )

    campaign = request.GET.get("campaign")
    if campaign:
        qs = qs.filter(registration__campaign__slug=campaign.strip())

    template_key = request.GET.get("template_key")
    if template_key:
        qs = qs.filter(template_key=template_key.strip())

    status = request.GET.get("status")
    if status:
        qs = qs.filter(status=status.strip().lower())

    limit = _parse_limit(request.GET.get("limit"))
    rows = qs.order_by("-created_at", "-id")[:limit]

    notifications = [_serialize_notification(n) for n in rows]
    payload = {
        "notifications": notifications,
        "count": len(notifications),
    }
    if raw_reg_id:
        payload["registration"] = (
            _serialize_registration(registration_obj)
            if registration_obj is not None
            else None
        )
    return JsonResponse(payload)


def _parse_limit(raw_value) -> int:
    if not raw_value:
        return DEFAULT_LIMIT
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT
    if value < 1:
        return DEFAULT_LIMIT
    return min(value, MAX_LIMIT)


def _iso(dt):
    return dt.isoformat() if dt else None


def _serialize_registration(reg) -> dict:
    return {
        "id": reg.pk,
        "campaign": reg.campaign.slug if reg.campaign_id else None,
        "course": reg.course.slug if reg.course_id else None,
        "email": reg.email_normalized,
        "name": reg.name,
        "status": reg.status,
        "source": reg.source,
        "email_confirmed": reg.email_confirmed,
        "email_confirmation_sent_at": _iso(reg.email_confirmation_sent_at),
        "created_at": _iso(reg.created_at),
        "updated_at": _iso(reg.updated_at),
        "auto_approved_at": _iso(reg.auto_approved_at),
    }


def _serialize_notification(notification) -> dict:
    return {
        "id": notification.pk,
        "registration_id": notification.registration_id,
        "campaign": (
            notification.registration.campaign.slug
            if notification.registration and notification.registration.campaign_id
            else None
        ),
        "course": (
            notification.registration.course.slug
            if notification.registration and notification.registration.course_id
            else None
        ),
        "recipient": notification.recipient,
        "template_key": notification.template_key,
        "decision_sequence": notification.decision_sequence,
        "idempotency_key": str(notification.idempotency_key),
        "relay_idempotency_key": f"cmp-application:{notification.idempotency_key}",
        "status": notification.status,
        "attempt_count": notification.attempt_count,
        "last_error": notification.last_error,
        "relay_message_id": notification.relay_message_id,
        "created_at": _iso(notification.created_at),
        "updated_at": _iso(notification.updated_at),
        "last_attempt_at": _iso(notification.last_attempt_at),
        "next_attempt_at": _iso(notification.next_attempt_at),
        "registration": _serialize_registration(notification.registration),
    }
