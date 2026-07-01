from django.contrib import messages
from django.db.models import Count, Sum
from django.shortcuts import redirect
from django.utils import timezone

from course_management.datamailer_outbox_status import (
    datamailer_outbox_status_summary,
)
from data.models import (
    DatamailerOutboxEvent,
    DatamailerOutboxStatus,
    DatamailerSendAudit,
    DatamailerSendAuditStatus,
)


DATAMAILER_RECIPIENT_LIST_KINDS = [
    "registrations",
    "enrollments",
    "homework",
    "project",
    "project-passed",
    "graduates",
]

DATAMAILER_OPERATOR_COMMANDS = (
    {
        "title": "Bootstrap contacts",
        "description": "Load active CMP users into Datamailer contacts.",
        "command": "uv run python manage.py sync_datamailer_contacts --active-only",
    },
    {
        "title": "Bootstrap recipient lists",
        "description": (
            "Load the target path-key audience tree from CMP source data."
        ),
        "command": (
            "uv run python manage.py sync_datamailer_recipient_lists "
            "<kind> --reconcile"
        ),
    },
    {
        "title": "Audit list drift",
        "description": (
            "Compare one CMP recipient-list source with Datamailer members."
        ),
        "command": (
            "uv run python manage.py audit_datamailer_recipient_lists "
            "<kind> --fail-on-drift"
        ),
    },
    {
        "title": "Repair list drift",
        "description": (
            "Reconcile Datamailer to the CMP snapshot for one source."
        ),
        "command": (
            "uv run python manage.py audit_datamailer_recipient_lists "
            "<kind> --repair"
        ),
    },
)


def send_audit_totals():
    total_count = Count("id")
    intended_count_sum = Sum("intended_count")
    created_count_sum = Sum("created_count")
    enqueued_count_sum = Sum("enqueued_count")
    skipped_count_sum = Sum("skipped_count")
    idempotent_replay_count_sum = Sum("idempotent_replay_count")

    return DatamailerSendAudit.objects.aggregate(
        total=total_count,
        intended_count=intended_count_sum,
        created_count=created_count_sum,
        enqueued_count=enqueued_count_sum,
        skipped_count=skipped_count_sum,
        idempotent_replay_count=idempotent_replay_count_sum,
    )


def send_audit_grouped(field):
    group_count = Count("id")
    intended_count_sum = Sum("intended_count")
    enqueued_count_sum = Sum("enqueued_count")
    skipped_count_sum = Sum("skipped_count")
    rows = (
        DatamailerSendAudit.objects.values(field)
        .annotate(
            count=group_count,
            intended_count=intended_count_sum,
            enqueued_count=enqueued_count_sum,
            skipped_count=skipped_count_sum,
        )
        .order_by(field)
    )
    return list(rows)


def requeue_datamailer_outbox_events():
    now = timezone.now()
    return DatamailerOutboxEvent.objects.filter(
        status__in=[
            DatamailerOutboxStatus.FAILED,
            DatamailerOutboxStatus.DEAD,
        ]
    ).update(
        status=DatamailerOutboxStatus.RETRYING,
        next_attempt_at=now,
        last_error="",
        updated_at=now,
    )


def handle_datamailer_operations_post(request):
    if request.POST.get("action") != "requeue":
        return None

    requeued = requeue_datamailer_outbox_events()
    messages.success(
        request,
        f"Requeued {requeued} Datamailer outbox event(s).",
    )
    response = redirect("cadmin_datamailer_operations")
    return response


def recent_failed_datamailer_outbox_events():
    return DatamailerOutboxEvent.objects.filter(
        status__in=[
            DatamailerOutboxStatus.RETRYING,
            DatamailerOutboxStatus.FAILED,
            DatamailerOutboxStatus.DEAD,
        ]
    ).exclude(last_error="")[:10]


def recent_failed_datamailer_sends():
    return DatamailerSendAudit.objects.filter(
        status=DatamailerSendAuditStatus.FAILED,
    )[:10]


def failed_datamailer_send_count():
    return DatamailerSendAudit.objects.filter(
        status=DatamailerSendAuditStatus.FAILED,
    ).count()


def normalized_send_totals(send_totals):
    total = send_totals["total"] or 0
    intended_count = send_totals["intended_count"] or 0
    created_count = send_totals["created_count"] or 0
    enqueued_count = send_totals["enqueued_count"] or 0
    skipped_count = send_totals["skipped_count"] or 0
    idempotent_replay_count = send_totals["idempotent_replay_count"] or 0
    failed = failed_datamailer_send_count()

    return {
        "total": total,
        "intended_count": intended_count,
        "created_count": created_count,
        "enqueued_count": enqueued_count,
        "skipped_count": skipped_count,
        "idempotent_replay_count": idempotent_replay_count,
        "failed": failed,
    }


def datamailer_outbox_status_rows(outbox_summary):
    rows = []

    for status in DatamailerOutboxStatus.values:
        row = {
            "status": status,
            "count": outbox_summary["event_counts"].get(status, 0),
        }
        rows.append(row)
    return rows


def datamailer_operations_context():
    outbox_summary = datamailer_outbox_status_summary()
    outbox_statuses = datamailer_outbox_status_rows(outbox_summary)
    recent_failed_events = recent_failed_datamailer_outbox_events()
    send_totals = send_audit_totals()
    normalized_totals = normalized_send_totals(send_totals)
    send_by_status = send_audit_grouped("status")
    send_by_type = send_audit_grouped("send_type")
    recent_failed_sends = recent_failed_datamailer_sends()

    return {
        "outbox_summary": outbox_summary,
        "outbox_statuses": outbox_statuses,
        "recent_failed_events": recent_failed_events,
        "send_totals": normalized_totals,
        "send_by_status": send_by_status,
        "send_by_type": send_by_type,
        "recent_failed_sends": recent_failed_sends,
        "operator_commands": DATAMAILER_OPERATOR_COMMANDS,
        "recipient_list_kinds": DATAMAILER_RECIPIENT_LIST_KINDS,
    }
