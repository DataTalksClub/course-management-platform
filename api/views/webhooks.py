import hmac
import json
from dataclasses import dataclass

from django.conf import settings
from django.db.models import F
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from data.models import DatamailerContactEvent


SUPPORTED_EVENT_TYPES = {
    "contact.hard_bounced",
    "contact.complained",
    "subscription.unsubscribed",
    "subscription.resubscribed",
    "message.delivered",
    "message.opened",
    "message.clicked",
    "transactional.skipped",
    "transactional.failed",
}
PREFERENCE_FIELDS = {
    "email_submission_confirmations",
    "email_deadline_reminders",
    "email_course_updates",
}


@dataclass(frozen=True)
class DatamailerEventFields:
    event_id: str
    event_type: str
    email: str


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
    candidates = preference_key_candidates(payload)
    for preference_key in candidates:
        if preference_key in PREFERENCE_FIELDS:
            return preference_key
    return ""


def preference_key_candidates(payload):
    metadata = payload_metadata(payload)
    candidates = [
        payload.get("preference_key"),
        metadata.get("preference_key"),
        metadata.get("cmp_preference_key"),
    ]
    return candidates


def payload_metadata(payload):
    return payload.get("metadata") or {}


def webhook_error(message, status):
    return JsonResponse({"error": message}, status=status)


def datamailer_webhook_configured() -> bool:
    return bool(getattr(settings, "DATAMAILER_WEBHOOK_TOKEN", ""))


def json_payload_from_request(request):
    try:
        return json.loads(request.body or b"{}"), None
    except json.JSONDecodeError:
        return None, webhook_error("Invalid JSON", 400)


def required_event_fields(payload):
    fields = DatamailerEventFields(
        event_id=str(payload.get("event_id") or "").strip(),
        event_type=str(payload.get("event_type") or "").strip(),
        email=str(payload.get("email") or "").strip().lower(),
    )
    return fields


def validate_datamailer_payload(payload):
    fields = required_event_fields(payload)
    if not fields.event_id or not fields.event_type or not fields.email:
        return None, webhook_error(
            "event_id, event_type, and email are required",
            400,
        )
    if fields.event_type not in SUPPORTED_EVENT_TYPES:
        return None, webhook_error(
            f"Unsupported event_type: {fields.event_type}",
            400,
        )
    return fields, None


def parsed_occurred_at(payload):
    occurred_at = payload.get("occurred_at")
    if isinstance(occurred_at, str):
        return parse_datetime(occurred_at)
    return None


def datamailer_event_defaults(payload, event_type, email):
    return {
        "event_type": event_type,
        "email": email,
        "occurred_at": parsed_occurred_at(payload),
        "audience": str(payload.get("audience") or ""),
        "client": str(payload.get("client") or ""),
        "preference_key": preference_key_from_payload(payload),
        "payload": payload,
        "last_seen_at": timezone.now(),
    }


def update_duplicate_datamailer_event(event):
    DatamailerContactEvent.objects.filter(pk=event.pk).update(
        duplicate_count=F("duplicate_count") + 1,
        last_seen_at=timezone.now(),
    )
    event.refresh_from_db(fields=["duplicate_count", "last_seen_at"])


def record_datamailer_event(payload, fields):
    event, created = DatamailerContactEvent.objects.get_or_create(
        event_id=fields.event_id,
        defaults=datamailer_event_defaults(
            payload,
            fields.event_type,
            fields.email,
        ),
    )
    if not created:
        update_duplicate_datamailer_event(event)
    return event, created


def datamailer_event_response(event, created):
    return JsonResponse(
        {
            "ok": True,
            "created": created,
            "duplicate_count": event.duplicate_count,
            "preference_updated": False,
        }
    )


@csrf_exempt
@require_POST
def datamailer_event_webhook(request):
    if not datamailer_webhook_configured():
        return webhook_error(
            "Datamailer webhook is not configured", 503
        )
    if not authenticate_webhook(request):
        return webhook_error("Unauthorized", 401)

    payload, error = json_payload_from_request(request)
    if error is not None:
        return error

    fields, error = validate_datamailer_payload(payload)
    if error is not None:
        return error

    event, created = record_datamailer_event(payload, fields)
    return datamailer_event_response(event, created)
