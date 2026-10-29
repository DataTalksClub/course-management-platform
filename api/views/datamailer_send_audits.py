from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from accounts.auth import token_required
from api.safety import require_staff_token
from course_management.datamailer.send_audit_skips import (
    send_audit_skipped_recipients,
)
from data.models import DatamailerOutboxEvent, DatamailerSendAudit

DEFAULT_LIMIT = 25
MAX_LIMIT = 100


@require_GET
@token_required
def datamailer_send_audits_view(request):
    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    audits = DatamailerSendAudit.objects.all()

    email = request.GET.get("email")
    if email:
        # The recipient is stored under response_payload["message"]["email"].
        # It is persisted lowercased, so lowercase the query value to match.
        audits = audits.filter(
            response_payload__message__email=email.strip().lower()
        )

    template_key = request.GET.get("template_key")
    if template_key:
        audits = audits.filter(template_key=template_key)

    idempotency_key = request.GET.get("idempotency_key")
    if idempotency_key:
        audits = audits.filter(idempotency_key=idempotency_key)

    status = request.GET.get("status")
    if status:
        audits = audits.filter(status=status.strip().lower())

    send_type = request.GET.get("send_type")
    if send_type:
        audits = audits.filter(send_type=send_type.strip().lower())

    limit = _parse_limit(request.GET.get("limit"))
    audits = audits.order_by("-occurred_at")[:limit]

    records = []
    for audit in audits:
        records.append(_serialize_audit(audit))

    response = {"audits": records, "count": len(records)}
    if idempotency_key:
        response["outbox_events"] = _outbox_diagnostics(idempotency_key)
    return JsonResponse(response)


@require_GET
@token_required
def datamailer_send_audit_detail_view(request, audit_id):
    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    audit = get_object_or_404(DatamailerSendAudit, pk=audit_id)
    response = _serialize_audit(audit, lookup_skips=True)
    response["outbox_events"] = _outbox_diagnostics(audit.idempotency_key)
    return JsonResponse(response)


def _outbox_diagnostics(idempotency_key):
    # An exact key is required; never expose member payloads or responses.
    keys = [
        idempotency_key,
        f"recipient-list.members-bulk-upsert:{idempotency_key}:members",
    ]
    events = DatamailerOutboxEvent.objects.filter(
        idempotency_key__in=keys,
    ).order_by("-created_at", "-id")[:20]
    return list(events.values(
        "event_type", "status", "attempt_count", "max_attempts", "last_error",
        "created_at", "updated_at", "next_attempt_at", "last_attempt_at",
    ))


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


def _serialize_audit(audit, *, lookup_skips=False) -> dict:
    payload = audit.response_payload or {}
    message = payload.get("message") or {}
    rendered = payload.get("rendered") or {}
    would_deliver = payload.get("would_deliver")

    occurred_at = None
    if audit.occurred_at:
        occurred_at = audit.occurred_at.isoformat()

    data = {
        "id": audit.pk,
        "send_type": audit.send_type,
        "status": audit.status,
        "template_key": audit.template_key,
        "idempotency_key": audit.idempotency_key,
        "list_key": audit.list_key,
        "occurred_at": occurred_at,
        # Without this a failed send is indistinguishable from a silent
        # no-op: response_payload is empty when the request never landed.
        "error": audit.error,
        "intended_count": audit.intended_count,
        "enqueued_count": audit.enqueued_count,
        "skipped_count": audit.skipped_count,
        "would_deliver": would_deliver,
        "rendered": rendered,
        "message": message,
        "response_payload": payload,
    }
    data.update(
        send_audit_skipped_recipients(audit, lookup=lookup_skips)
    )
    return data
