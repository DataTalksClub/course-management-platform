from django.db.models import Count, Sum

from data.models import (
    DatamailerSendAudit,
    DatamailerSendAuditStatus,
)

SEND_TOTAL_FIELDS = (
    "total",
    "intended_count",
    "created_count",
    "enqueued_count",
    "skipped_count",
    "idempotent_replay_count",
)


def send_audit_totals():
    total_count = Count("id")
    intended_count_sum = Sum("intended_count")
    created_count_sum = Sum("created_count")
    enqueued_count_sum = Sum("enqueued_count")
    skipped_count_sum = Sum("skipped_count")
    idempotent_replay_count_sum = Sum("idempotent_replay_count")

    totals = DatamailerSendAudit.objects.aggregate(
        total=total_count,
        intended_count=intended_count_sum,
        created_count=created_count_sum,
        enqueued_count=enqueued_count_sum,
        skipped_count=skipped_count_sum,
        idempotent_replay_count=idempotent_replay_count_sum,
    )
    return totals


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
    grouped_rows = list(rows)
    return grouped_rows


def recent_failed_datamailer_sends():
    sends = DatamailerSendAudit.objects.filter(
        status=DatamailerSendAuditStatus.FAILED,
    )[:10]
    return sends


def normalized_send_totals(send_totals):
    totals = {}
    for field in SEND_TOTAL_FIELDS:
        value = send_totals[field] or 0
        totals[field] = value

    failed_sends = DatamailerSendAudit.objects.filter(
        status=DatamailerSendAuditStatus.FAILED,
    )
    failed_count = failed_sends.count()
    totals["failed"] = failed_count

    return totals
