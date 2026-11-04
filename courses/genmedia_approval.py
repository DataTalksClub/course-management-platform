"""Evening bulk approval for the Production AI Agents campaign.

Runs once per Europe/Berlin day inside the 20:00 hour. The Berlin-local
hour guard gives a single run across DST (no dual UTC cron needed when
piggybacked on the minutely outbox tick); one ``GenmediaApprovalRun``
row per Berlin date plus ``worker_lock`` make restarts and rolling
replicas safe.

Stops approving once 2000 registrations exist for the campaign course.

Sends NO emails to registrants: approvals use ``bulk_update`` (never
``.save()``), so no ``ApplicationNotification`` rows are queued and the
Relay outbox stays untouched. The only mail sent is the operator-only
Nebius report (approved-list CSV to Mikhail + Alexey copy) via
``courses.genmedia_report``; it never raises and never touches registrants.
"""

import logging
from dataclasses import dataclass
from datetime import date
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from course_management.observability import record_event
from course_management.worker_lock import worker_lock
from courses.genmedia_policy import (
    AUTO_APPROVAL_HOUR,
    AUTO_APPROVAL_LIMIT,
    AUTO_APPROVAL_TIMEZONE,
    CAMPAIGN_SLUG,
    excluded_reason,
)
from courses.models.genmedia_approval import GenmediaApprovalRun

logger = logging.getLogger(__name__)

APPROVAL_TIMEZONE = ZoneInfo(AUTO_APPROVAL_TIMEZONE)
APPROVAL_JOB = "genmedia"


@dataclass
class ApprovalResult:
    ran: bool
    reason: str
    day: "date | None" = None
    approved: int = 0
    excluded: int = 0
    stopped_at_limit: bool = False


def approval_moment(now=None):
    return now if now is not None else timezone.now()


def approval_day(now=None) -> date:
    return approval_moment(now).astimezone(APPROVAL_TIMEZONE).date()


def approval_due(now=None) -> bool:
    """True once per Europe/Berlin day inside the 20:00 hour until run."""
    moment = approval_moment(now)
    berlin = moment.astimezone(APPROVAL_TIMEZONE)
    if berlin.hour != AUTO_APPROVAL_HOUR:
        return False
    return not GenmediaApprovalRun.objects.filter(date=berlin.date()).exists()


def approve_pending_registrations(now=None) -> ApprovalResult:
    """Approve eligible pending applicants exactly once per Berlin day."""
    from courses.models.course import CourseRegistration, RegistrationCampaign

    moment = approval_moment(now)
    berlin = moment.astimezone(APPROVAL_TIMEZONE)
    day = berlin.date()
    if berlin.hour != AUTO_APPROVAL_HOUR:
        return ApprovalResult(ran=False, reason="not-due", day=day)
    with worker_lock(f"genmedia-approval:{day}") as acquired:
        if not acquired:
            return ApprovalResult(ran=False, reason="locked", day=day)
        with transaction.atomic():
            if GenmediaApprovalRun.objects.filter(date=day).exists():
                return ApprovalResult(
                    ran=False, reason="already-done", day=day
                )
            campaign = RegistrationCampaign.objects.filter(
                slug=CAMPAIGN_SLUG
            ).first()
            if campaign is None:
                return ApprovalResult(
                    ran=False, reason="no-campaign", day=day
                )
            registrations = list(
                CourseRegistration.objects.filter(
                    campaign=campaign,
                    course_id=campaign.current_course_id,
                    status=CourseRegistration.Status.PENDING,
                ).order_by("created_at", "pk")
            )
            total = CourseRegistration.objects.filter(
                campaign=campaign, course_id=campaign.current_course_id
            ).count()
            if total >= AUTO_APPROVAL_LIMIT:
                GenmediaApprovalRun.objects.create(
                    date=day,
                    status=GenmediaApprovalRun.Status.STOPPED_AT_LIMIT,
                    approved_count=0,
                    excluded_count=sum(
                        bool(excluded_reason(row)) for row in registrations
                    ),
                )
                return ApprovalResult(
                    ran=True,
                    reason="stopped-at-limit",
                    day=day,
                    approved=0,
                    excluded=len(registrations)
                    - len(
                        [
                            row
                            for row in registrations
                            if not excluded_reason(row)
                        ]
                    ),
                    stopped_at_limit=True,
                )
            eligible = [
                row for row in registrations if not excluded_reason(row)
            ]
            approved_at = timezone.now()
            for registration in eligible:
                registration.status = CourseRegistration.Status.APPROVED
                registration.auto_approved_at = approved_at
                registration.updated_at = approved_at
            # bulk_update on purpose: per-object .save() would queue
            # registrant-facing decision emails. Bulk approval is silent.
            CourseRegistration.objects.bulk_update(
                eligible, ["status", "auto_approved_at", "updated_at"]
            )
            # Points are not emails: accepted invitees still earn their
            # referrer the bonus. Idempotent per invitee.
            from courses.referrals import award_referral_bonus

            for registration in eligible:
                try:
                    award_referral_bonus(registration)
                except Exception:
                    logger.error(
                        "genmedia referral award failed registration_id=%s",
                        registration.pk,
                    )
            GenmediaApprovalRun.objects.create(
                date=day,
                status=GenmediaApprovalRun.Status.COMPLETED,
                approved_count=len(eligible),
                excluded_count=len(registrations) - len(eligible),
            )
    if eligible:
        # Operator-only CSV report (Nebius + Alexey copy). Skipped when
        # nothing was approved; never raises and never emails registrants.
        try:
            from courses import genmedia_report

            genmedia_report.send_nebius_report(
                day=day,
                approved=eligible,
                excluded_count=len(registrations) - len(eligible),
            )
        except Exception:
            logger.error("genmedia nebius report failed day=%s", day)
    try:
        record_event("genmedia.nightly-approval", properties={
            "source": "genmedia-approval",
            "date": day.isoformat(),
            "approved": len(eligible),
            "excluded": len(registrations) - len(eligible),
        })
    except Exception:
        logger.error("genmedia approval observability event failed")
    return ApprovalResult(
        ran=True,
        reason="completed",
        day=day,
        approved=len(eligible),
        excluded=len(registrations) - len(eligible),
    )


def maybe_run_scheduled_approval(now=None):
    """Best-effort nightly hook for the minutely outbox schedule.

    Returns an ApprovalResult (or None when not due). Never raises:
    approval trouble must not block Datamailer outbox processing, and
    must never send mail.
    """
    moment = approval_moment(now)
    try:
        if not approval_due(moment):
            return None
        return approve_pending_registrations(now=moment)
    except Exception as exc:
        logger.error(
            "Scheduled genmedia approval skipped error=%s",
            type(exc).__name__,
        )
        return ApprovalResult(
            ran=False,
            reason="failed",
            day=moment.astimezone(APPROVAL_TIMEZONE).date(),
        )
