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
        token = authorization[len(prefix) :]
        stripped_token = token.strip()
        return stripped_token
    header_token = request.headers.get("X-Datamailer-Webhook-Token", "")
    stripped_header_token = header_token.strip()
    return stripped_header_token


def authenticate_webhook(request):
    expected = getattr(settings, "DATAMAILER_WEBHOOK_TOKEN", "")
    if not expected:
        return False
    token = bearer_token(request)
    return hmac.compare_digest(token, expected)


def preference_key_from_payload(payload):
    candidates = preference_key_candidates(payload)
    for preference_key in candidates:
        if preference_key in PREFERENCE_FIELDS:
            return preference_key
    return ""


def preference_key_candidates(payload):
    metadata = payload_metadata(payload)
    preference_key = payload.get("preference_key")
    metadata_preference_key = metadata.get("preference_key")
    cmp_preference_key = metadata.get("cmp_preference_key")
    candidates = [
        preference_key,
        metadata_preference_key,
        cmp_preference_key,
    ]
    return candidates


def payload_metadata(payload):
    metadata = payload.get("metadata")
    if metadata:
        return metadata
    return {}


def webhook_error(message, status):
    payload = {"error": message}
    response = JsonResponse(payload, status=status)
    return response


def json_payload_from_request(request):
    try:
        body = request.body or b"{}"
        payload = json.loads(body)
        return payload, None
    except json.JSONDecodeError:
        error = webhook_error("Invalid JSON", 400)
        return None, error


def required_event_fields(payload):
    event_id = payload.get("event_id") or ""
    event_id = str(event_id).strip()
    event_type = payload.get("event_type") or ""
    event_type = str(event_type).strip()
    email = payload.get("email") or ""
    email = str(email).strip().lower()
    fields = DatamailerEventFields(
        event_id=event_id,
        event_type=event_type,
        email=email,
    )
    return fields


def validate_datamailer_payload(payload):
    fields = required_event_fields(payload)
    if not fields.event_id or not fields.event_type or not fields.email:
        error = webhook_error(
            "event_id, event_type, and email are required",
            400,
        )
        return None, error
    if fields.event_type not in SUPPORTED_EVENT_TYPES:
        error = webhook_error(
            f"Unsupported event_type: {fields.event_type}",
            400,
        )
        return None, error
    return fields, None


def parsed_occurred_at(payload):
    occurred_at = payload.get("occurred_at")
    if isinstance(occurred_at, str):
        parsed = parse_datetime(occurred_at)
        return parsed
    return None


def datamailer_event_defaults(payload, event_type, email):
    occurred_at = parsed_occurred_at(payload)
    audience = payload.get("audience") or ""
    audience = str(audience)
    client = payload.get("client") or ""
    client = str(client)
    preference_key = preference_key_from_payload(payload)
    last_seen_at = timezone.now()
    return {
        "event_type": event_type,
        "email": email,
        "occurred_at": occurred_at,
        "audience": audience,
        "client": client,
        "preference_key": preference_key,
        "payload": payload,
        "last_seen_at": last_seen_at,
    }


def update_duplicate_datamailer_event(event):
    duplicate_count = F("duplicate_count") + 1
    last_seen_at = timezone.now()
    DatamailerContactEvent.objects.filter(pk=event.pk).update(
        duplicate_count=duplicate_count,
        last_seen_at=last_seen_at,
    )
    event.refresh_from_db(fields=["duplicate_count", "last_seen_at"])


def record_datamailer_event(payload, fields):
    defaults = datamailer_event_defaults(
        payload,
        fields.event_type,
        fields.email,
    )
    event, created = DatamailerContactEvent.objects.get_or_create(
        event_id=fields.event_id,
        defaults=defaults,
    )
    if not created:
        update_duplicate_datamailer_event(event)
    return event, created


def datamailer_event_response(event, created):
    payload = {
        "ok": True,
        "created": created,
        "duplicate_count": event.duplicate_count,
        "preference_updated": False,
    }
    response = JsonResponse(payload)
    return response


@csrf_exempt
@require_POST
def datamailer_event_webhook(request):
    webhook_token = getattr(settings, "DATAMAILER_WEBHOOK_TOKEN", "")
    if not webhook_token:
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
