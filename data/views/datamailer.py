import hmac
import json

from django.conf import settings
from django.http import JsonResponse
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt

from accounts.models import CustomUser
from data.models import DatamailerContactEvent


SUPPORTED_EVENT_TYPES = {
    "contact.hard_bounced",
    "contact.complained",
    "subscription.unsubscribed",
}
PREFERENCE_FIELDS = {
    "email_submission_confirmations",
    "email_deadline_reminders",
    "email_course_updates",
}


def bearer_token(request):
    authorization = request.headers.get("Authorization", "")
    prefix = "Bearer "
    if authorization.startswith(prefix):
        return authorization[len(prefix) :].strip()
    return request.headers.get("X-Datamailer-Webhook-Token", "").strip()


def authenticate_webhook(request):
    expected = getattr(settings, "DATAMAILER_WEBHOOK_TOKEN", "")
    if not expected:
        return False
    return hmac.compare_digest(bearer_token(request), expected)


def preference_key_from_payload(payload):
    metadata = payload.get("metadata") or {}
    preference_key = (
        payload.get("preference_key")
        or metadata.get("preference_key")
        or metadata.get("cmp_preference_key")
        or ""
    )
    return preference_key if preference_key in PREFERENCE_FIELDS else ""


def apply_unsubscribe_preference(email, preference_key):
    if not preference_key:
        return False

    updated = CustomUser.objects.filter(email__iexact=email).update(
        **{preference_key: False}
    )
    return updated > 0


@csrf_exempt
def datamailer_event_webhook(request):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    if not getattr(settings, "DATAMAILER_WEBHOOK_TOKEN", ""):
        return JsonResponse(
            {"error": "Datamailer webhook is not configured"},
            status=503,
        )
    if not authenticate_webhook(request):
        return JsonResponse({"error": "Unauthorized"}, status=401)

    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    event_id = str(payload.get("event_id") or "").strip()
    event_type = str(payload.get("event_type") or "").strip()
    email = str(payload.get("email") or "").strip().lower()
    if not event_id or not event_type or not email:
        return JsonResponse(
            {"error": "event_id, event_type, and email are required"},
            status=400,
        )
    if event_type not in SUPPORTED_EVENT_TYPES:
        return JsonResponse(
            {"error": f"Unsupported event_type: {event_type}"},
            status=400,
        )

    occurred_at = payload.get("occurred_at")
    parsed_occurred_at = (
        parse_datetime(occurred_at)
        if isinstance(occurred_at, str)
        else None
    )
    preference_key = preference_key_from_payload(payload)
    event, created = DatamailerContactEvent.objects.get_or_create(
        event_id=event_id,
        defaults={
            "event_type": event_type,
            "email": email,
            "occurred_at": parsed_occurred_at,
            "audience": str(payload.get("audience") or ""),
            "client": str(payload.get("client") or ""),
            "preference_key": preference_key,
            "payload": payload,
        },
    )

    preference_updated = False
    if created and event.event_type == "subscription.unsubscribed":
        preference_updated = apply_unsubscribe_preference(
            event.email,
            event.preference_key,
        )

    return JsonResponse(
        {
            "ok": True,
            "created": created,
            "preference_updated": preference_updated,
        }
    )
