from django.contrib import messages
from django.shortcuts import redirect

from course_management.datamailer_outbox_status import (
    datamailer_outbox_status_summary,
)
from .datamailer_outbox_operations import (
    datamailer_outbox_status_rows,
    recent_failed_datamailer_outbox_events,
    requeue_datamailer_outbox_events,
)
from .datamailer_send_audits import (
    normalized_send_totals,
    recent_failed_datamailer_sends,
    send_audit_grouped,
    send_audit_totals,
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
