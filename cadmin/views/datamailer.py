from datetime import timedelta

from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.shortcuts import redirect, render
from django.utils import timezone

from course_management.datamailer_outbox import (
    datamailer_outbox_status_summary,
)
from data.models import (
    DatamailerContactEvent,
    DatamailerOutboxEvent,
    DatamailerOutboxStatus,
    DatamailerSendAudit,
    DatamailerSendAuditStatus,
)

from .helpers import (
    count_by,
    paginate_queryset,
    pagination_querystring,
    staff_required,
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


@staff_required
def datamailer_operations(request):
    if request.method == "POST":
        response = handle_datamailer_operations_post(request)
        if response is not None:
            return response

    context = datamailer_operations_context()
    response = render(
        request,
        "cadmin/datamailer_operations.html",
        context,
    )
    return response


def datamailer_event_filters(request):
    return (
        request.GET.get("event_type", "").strip(),
        request.GET.get("q", "").strip(),
    )


def filtered_datamailer_events(event_type, search_query):
    events = DatamailerContactEvent.objects.all()

    if event_type:
        events = events.filter(event_type=event_type)
    if search_query:
        events = events.filter(
            Q(email__icontains=search_query)
            | Q(event_id__icontains=search_query)
            | Q(client__icontains=search_query)
            | Q(audience__icontains=search_query)
            | Q(preference_key__icontains=search_query)
        )

    return events


def datamailer_events_metrics():
    since = timezone.now() - timedelta(hours=24)
    total = DatamailerContactEvent.objects.count()
    last_24h = DatamailerContactEvent.objects.filter(
        created_at__gte=since
    ).count()
    duplicate_count_sum = Sum("duplicate_count")
    duplicate_aggregate = DatamailerContactEvent.objects.aggregate(
        total=duplicate_count_sum
    )
    duplicates = duplicate_aggregate["total"] or 0
    events = DatamailerContactEvent.objects.all()
    by_type = count_by(events, "event_type")

    return {
        "total": total,
        "last_24h": last_24h,
        "duplicates": duplicates,
        "by_type": by_type,
    }


def datamailer_events_context(
    request, events, event_type, search_query
):
    events_page = paginate_queryset(request, events, per_page=50)
    event_type_values = (
        DatamailerContactEvent.objects.order_by("event_type")
        .values_list("event_type", flat=True)
        .distinct()
    )
    event_types = list(event_type_values)
    metrics = datamailer_events_metrics()
    page_range = events_page.paginator.get_elided_page_range(
        events_page.number
    )
    querystring = pagination_querystring(request)

    return {
        "events_page": events_page,
        "event_types": event_types,
        "selected_event_type": event_type,
        "search_query": search_query,
        "metrics": metrics,
        "page_range": page_range,
        "pagination_querystring": querystring,
    }


@staff_required
def datamailer_events(request):
    event_type, search_query = datamailer_event_filters(request)
    events = filtered_datamailer_events(event_type, search_query)
    context = datamailer_events_context(
        request, events, event_type, search_query
    )

    response = render(
        request,
        "cadmin/datamailer_events.html",
        context,
    )
    return response
