"""Send-once guard for the peer-review-assignment recipient-list send.

The DatamailerSendAudit row for ``peer-review-assignment:<course>:<project>``
doubles as the send-once marker: a ``pending`` row is the in-flight claim, a
``succeeded`` row blocks further sends, and a ``failed`` row may be reclaimed.
The unique (send_type, idempotency_key) constraint makes the claim race-safe.
"""

import logging

from django.db import IntegrityError, transaction
from django.utils import timezone

from course_management import email_templates
from data.models import (
    DatamailerSendAudit,
    DatamailerSendAuditStatus,
    DatamailerSendAuditType,
)

from .peer_review_notifications import (
    send_peer_review_assignment_notification,
)


logger = logging.getLogger(__name__)

BLOCKING_STATUSES = (
    DatamailerSendAuditStatus.SUCCEEDED,
    DatamailerSendAuditStatus.PENDING,
)


class PeerReviewNotificationAlreadySent(Exception):
    def __init__(self, audit):
        super().__init__(audit.idempotency_key)
        self.audit = audit


def peer_review_assignment_idempotency_key(project) -> str:
    return f"peer-review-assignment:{project.course.slug}:{project.slug}"


def _audits_for(project):
    return DatamailerSendAudit.objects.filter(
        send_type=DatamailerSendAuditType.RECIPIENT_LIST,
        idempotency_key=peer_review_assignment_idempotency_key(project),
    )


def peer_review_assignment_send_audit(project):
    return _audits_for(project).first()


def _claim(project):
    now = timezone.now()
    try:
        with transaction.atomic():
            return DatamailerSendAudit.objects.create(
                send_type=DatamailerSendAuditType.RECIPIENT_LIST,
                idempotency_key=peer_review_assignment_idempotency_key(
                    project
                ),
                status=DatamailerSendAuditStatus.PENDING,
                template_key=email_templates.PEER_REVIEW_ASSIGNMENT,
                source="course-management-platform",
                event="peer_review_assignment",
                occurred_at=now,
            )
    except IntegrityError:
        pass

    # Only one concurrent caller can flip a failed row back to pending.
    reclaimed = _audits_for(project).filter(
        status=DatamailerSendAuditStatus.FAILED,
    ).update(
        status=DatamailerSendAuditStatus.PENDING,
        error="",
        occurred_at=now,
        updated_at=now,
    )
    audit = peer_review_assignment_send_audit(project)
    if not reclaimed:
        raise PeerReviewNotificationAlreadySent(audit)
    return audit


def _fail_unfinished_claim(audit, error):
    DatamailerSendAudit.objects.filter(
        pk=audit.pk,
        status=DatamailerSendAuditStatus.PENDING,
    ).update(
        status=DatamailerSendAuditStatus.FAILED,
        error=error,
        updated_at=timezone.now(),
    )


def send_peer_review_assignment_notification_once(project):
    """Send the assignment email unless a succeeded or in-flight send exists.

    Raises PeerReviewNotificationAlreadySent with the blocking audit.
    Returns the final send audit (succeeded or failed).
    """
    audit = _claim(project)
    try:
        send_peer_review_assignment_notification(project)
    except Exception as exc:
        logger.exception(
            "Peer review assignment send-once failed for project_id=%s",
            project.pk,
        )
        _fail_unfinished_claim(
            audit, f"Send raised {type(exc).__name__}: {exc}"
        )
    else:
        _fail_unfinished_claim(
            audit,
            "Send finished without a send audit for this key "
            "(check Relay configuration and relay-config audits)",
        )
    audit.refresh_from_db()
    return audit


def reset_peer_review_assignment_send_marker(project, reason):
    """Deliberately allow one more send. Returns the number of rows reset."""
    return _audits_for(project).filter(
        status__in=BLOCKING_STATUSES,
    ).update(
        status=DatamailerSendAuditStatus.FAILED,
        error=(
            f"Send-once marker reset by operator at "
            f"{timezone.now().isoformat()}: {reason}"
        ),
        updated_at=timezone.now(),
    )
