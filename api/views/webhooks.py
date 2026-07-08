from django.db.models import F
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from course_management.observability import record_event
from api.views.datamailer_webhook_validation import (
    datamailer_webhook_data,
    preference_key_from_payload,
)
from data.models import DatamailerContactEvent


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
    data, error = datamailer_webhook_data(request)
    if error is not None:
        return error

    payload = data.payload
    fields = data.fields

    event, created = record_datamailer_event(payload, fields)
    record_event(
        "datamailer.callback_received",
        properties={
            "event_id": event.event_id,
            "event_type": event.event_type,
            "created": created,
            "duplicate_count": event.duplicate_count,
            "client": event.client,
            "audience": event.audience,
        },
    )
    response = datamailer_event_response(event, created)
    return response
