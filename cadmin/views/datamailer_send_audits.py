from django.db.models import Count, Sum

from data.models import (
    DatamailerSendAudit,
    DatamailerSendAuditStatus,
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


def failed_datamailer_send_count():
    failed_count = DatamailerSendAudit.objects.filter(
        status=DatamailerSendAuditStatus.FAILED,
    ).count()
    return failed_count


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
