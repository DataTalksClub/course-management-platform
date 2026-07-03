from django.http import JsonResponse
from django.views.decorators.http import require_GET

from accounts.auth import token_required
from data.models import DatamailerSendAudit

DEFAULT_LIMIT = 25
MAX_LIMIT = 100


@require_GET
@token_required
def datamailer_send_audits_view(request):
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

    limit = _parse_limit(request.GET.get("limit"))
    audits = audits.order_by("-occurred_at")[:limit]

    records = []
    for audit in audits:
        records.append(_serialize_audit(audit))

    response = {"audits": records, "count": len(records)}
    return JsonResponse(response)


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


def _serialize_audit(audit) -> dict:
    payload = audit.response_payload or {}
    message = payload.get("message") or {}
    rendered = payload.get("rendered") or {}
    would_deliver = payload.get("would_deliver")

    occurred_at = None
    if audit.occurred_at:
        occurred_at = audit.occurred_at.isoformat()

    return {
        "send_type": audit.send_type,
        "status": audit.status,
        "template_key": audit.template_key,
        "idempotency_key": audit.idempotency_key,
        "occurred_at": occurred_at,
        "would_deliver": would_deliver,
        "rendered": rendered,
        "message": message,
        "response_payload": payload,
    }
