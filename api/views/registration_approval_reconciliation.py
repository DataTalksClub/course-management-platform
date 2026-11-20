from django.db.models import Prefetch
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from accounts.auth import token_required
from api.safety import require_staff_token
from course_management.relay.application_notifications import (
    approved_registrations_without_sent_notification,
)
from courses.models import ApplicationNotification, CourseRegistration, RegistrationCampaign


def _parse_bool(raw_value, default=True):
    if raw_value is None or raw_value == "":
        return default
    lowered = raw_value.strip().lower()
    if lowered in {"1", "true", "yes"}:
        return True
    if lowered in {"0", "false", "no"}:
        return False
    return default


def _iso(dt):
    return dt.isoformat() if dt else None


def _diagnose_missing(notifications):
    if not notifications:
        return "no_notification_row"
    statuses = {n.status for n in notifications}
    if ApplicationNotification.Status.FAILED in statuses:
        return "notification_failed"
    if ApplicationNotification.Status.SKIPPED in statuses:
        return "notification_suppressed"
    return "notification_pending"


@require_GET
@token_required
def registration_approval_notifications_reconcile_view(request):
    """Report approved registrations lacking a sent application-approved notification."""
    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    campaign_slug = (request.GET.get("campaign") or "").strip() or None
    active_only = _parse_bool(request.GET.get("active_only"), default=True)
    include_registrations = _parse_bool(
        request.GET.get("include_registrations"), default=True
    )

    campaigns_qs = RegistrationCampaign.objects.order_by("slug")
    if campaign_slug:
        campaigns_qs = campaigns_qs.filter(slug=campaign_slug)
    elif active_only:
        campaigns_qs = campaigns_qs.filter(is_active=True)

    missing_qs = (
        approved_registrations_without_sent_notification(
            grace_minutes=0, campaign_slug=campaign_slug
        )
        .select_related("campaign", "course")
        .prefetch_related(
            Prefetch(
                "application_notifications",
                queryset=ApplicationNotification.objects.filter(
                    template_key="application-approved"
                ).order_by("decision_sequence", "id"),
            )
        )
        .order_by("campaign__slug", "id")
    )
    if not campaign_slug and active_only:
        missing_qs = missing_qs.filter(campaign__is_active=True)

    missing_by_campaign = {}
    for reg in missing_qs:
        missing_by_campaign.setdefault(reg.campaign_id, []).append(reg)

    campaign_records = []
    total_approved = 0
    total_missing = 0

    for campaign in campaigns_qs:
        approved_count = CourseRegistration.objects.filter(
            campaign=campaign,
            status=CourseRegistration.Status.APPROVED,
        ).count()
        missing_regs = missing_by_campaign.get(campaign.pk, [])
        missing_count = len(missing_regs)
        sent_count = max(approved_count - missing_count, 0)
        total_approved += approved_count
        total_missing += missing_count

        entry = {
            "slug": campaign.slug,
            "title": campaign.title,
            "is_active": campaign.is_active,
            "approved_count": approved_count,
            "sent_count": sent_count,
            "missing_count": missing_count,
        }
        if include_registrations:
            entry["registrations"] = [
                {
                    "id": reg.pk,
                    "email": reg.email_normalized,
                    "name": reg.name,
                    "status": reg.status,
                    "source": reg.source,
                    "email_confirmed": reg.email_confirmed,
                    "created_at": _iso(reg.created_at),
                    "updated_at": _iso(reg.updated_at),
                    "auto_approved_at": _iso(reg.auto_approved_at),
                    "diagnosis": _diagnose_missing(
                        list(reg.application_notifications.all())
                    ),
                    "notifications": [
                        {
                            "id": n.pk,
                            "status": n.status,
                            "attempt_count": n.attempt_count,
                            "last_error": n.last_error,
                            "created_at": _iso(n.created_at),
                            "updated_at": _iso(n.updated_at),
                            "last_attempt_at": _iso(n.last_attempt_at),
                        }
                        for n in reg.application_notifications.all()
                    ],
                }
                for reg in missing_regs
            ]
        campaign_records.append(entry)

    return JsonResponse(
        {
            "campaigns": campaign_records,
            "totals": {
                "campaigns_checked": len(campaign_records),
                "approved_count": total_approved,
                "sent_count": max(total_approved - total_missing, 0),
                "missing_count": total_missing,
            },
        }
    )
