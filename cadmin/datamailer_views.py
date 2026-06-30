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

from .view_helpers import (
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
    return DatamailerSendAudit.objects.aggregate(
        total=Count("id"),
        intended_count=Sum("intended_count"),
        created_count=Sum("created_count"),
        enqueued_count=Sum("enqueued_count"),
        skipped_count=Sum("skipped_count"),
        idempotent_replay_count=Sum("idempotent_replay_count"),
    )


def send_audit_grouped(field):
    return list(
        DatamailerSendAudit.objects.values(field)
        .annotate(
            count=Count("id"),
            intended_count=Sum("intended_count"),
            enqueued_count=Sum("enqueued_count"),
            skipped_count=Sum("skipped_count"),
        )
        .order_by(field)
    )


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
    return redirect("cadmin_datamailer_operations")


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


def _send_total_count(send_totals, key):
    return send_totals[key] or 0


def failed_datamailer_send_count():
    return DatamailerSendAudit.objects.filter(
        status=DatamailerSendAuditStatus.FAILED,
    ).count()


def normalized_send_totals(send_totals):
    return {
        "total": _send_total_count(send_totals, "total"),
        "intended_count": _send_total_count(
            send_totals,
            "intended_count",
        ),
        "created_count": _send_total_count(send_totals, "created_count"),
        "enqueued_count": _send_total_count(
            send_totals,
            "enqueued_count",
        ),
        "skipped_count": _send_total_count(send_totals, "skipped_count"),
        "idempotent_replay_count": _send_total_count(
            send_totals,
            "idempotent_replay_count",
        ),
        "failed": failed_datamailer_send_count(),
    }


def datamailer_outbox_status_rows(outbox_summary):
    rows = []
    statuses = DatamailerOutboxStatus.values
    for status in statuses:
        row = {
            "status": status,
            "count": outbox_summary["event_counts"].get(status, 0),
        }
        rows.append(row)
    return rows


def datamailer_operations_context():
    outbox_summary = datamailer_outbox_status_summary()
    return {
        "outbox_summary": outbox_summary,
        "outbox_statuses": datamailer_outbox_status_rows(
            outbox_summary
        ),
        "recent_failed_events": recent_failed_datamailer_outbox_events(),
        "send_totals": normalized_send_totals(send_audit_totals()),
        "send_by_status": send_audit_grouped("status"),
        "send_by_type": send_audit_grouped("send_type"),
        "recent_failed_sends": recent_failed_datamailer_sends(),
        "operator_commands": DATAMAILER_OPERATOR_COMMANDS,
        "recipient_list_kinds": DATAMAILER_RECIPIENT_LIST_KINDS,
    }


@staff_required
def datamailer_operations(request):
    if request.method == "POST":
        response = handle_datamailer_operations_post(request)
        if response is not None:
            return response

    return render(
        request,
        "cadmin/datamailer_operations.html",
        datamailer_operations_context(),
    )


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
    return {
        "total": DatamailerContactEvent.objects.count(),
        "last_24h": DatamailerContactEvent.objects.filter(
            created_at__gte=since
        ).count(),
        "duplicates": DatamailerContactEvent.objects.aggregate(
            total=Sum("duplicate_count")
        )["total"]
        or 0,
        "by_type": count_by(
            DatamailerContactEvent.objects.all(), "event_type"
        ),
    }


def datamailer_events_context(request, events, event_type, search_query):
    events_page = paginate_queryset(request, events, per_page=50)
    event_types = list(
        DatamailerContactEvent.objects.order_by("event_type")
        .values_list("event_type", flat=True)
        .distinct()
    )
    return {
        "events_page": events_page,
        "event_types": event_types,
        "selected_event_type": event_type,
        "search_query": search_query,
        "metrics": datamailer_events_metrics(),
        "page_range": events_page.paginator.get_elided_page_range(
            events_page.number
        ),
        "pagination_querystring": pagination_querystring(request),
    }


@staff_required
def datamailer_events(request):
    event_type, search_query = datamailer_event_filters(request)
    events = filtered_datamailer_events(event_type, search_query)

    return render(
        request,
        "cadmin/datamailer_events.html",
        datamailer_events_context(
            request, events, event_type, search_query
        ),
    )
