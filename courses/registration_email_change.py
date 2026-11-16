"""Staff correction of a CourseRegistration email, without sending mail.

Writes bypass ``CourseRegistration.save`` (queryset ``update``) so no
application notification is queued and no approval side effects replay.
Relay lists are re-synced explicitly after commit; those are contact/list
membership upserts, never emails.
"""

import copy
from dataclasses import dataclass, field
from functools import partial

from allauth.account.models import EmailAddress
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.db import transaction
from django.db.models import Q

from accounts.models import CustomUser
from courses.models import CourseRegistration, Enrollment
from courses.registration_enrollment import reconcile_approved_registration


class EmailChangeError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


@dataclass
class EmailChangeResult:
    registration: CourseRegistration
    old_email: str
    new_email: str
    applied: bool
    user_id: int | None = None
    user_action: str = "none"  # none | linked | email_updated | already_linked
    enrollment_id: int | None = None
    enrollment_created: bool = False
    notes: list = field(default_factory=list)


def users_owning_email(email):
    verified = EmailAddress.objects.filter(
        email__iexact=email, verified=True,
    ).values("user_id")
    return list(CustomUser.objects.filter(
        Q(email__iexact=email) | Q(pk__in=verified),
    ).distinct()[:3])


def clean_new_email(raw):
    email = (raw or "").strip().lower() if isinstance(raw, str) else ""
    if not email:
        raise EmailChangeError("invalid_email", "email is required")
    try:
        EmailValidator()(email)
    except ValidationError:
        raise EmailChangeError("invalid_email", "Enter a valid email address")
    return email


def plan_user(registration, new_email, update_user):
    """Return (user, action). Raises EmailChangeError on conflicts."""
    owners = users_owning_email(new_email)
    linked = registration.user
    if linked is not None:
        others = [u for u in owners if u.pk != linked.pk]
        if others:
            raise EmailChangeError(
                "conflicting_user",
                f"Email {new_email} belongs to another user "
                f"(id {others[0].pk}); registration is linked to user "
                f"{linked.pk}",
                status=409,
            )
        if (linked.email or "").lower() == new_email:
            return linked, "already_linked"
        if not update_user:
            return linked, "none"
        return linked, "email_updated"
    if len(owners) > 1:
        raise EmailChangeError(
            "conflicting_user",
            f"Several users own {new_email}; refusing to pick one",
            status=409,
        )
    if len(owners) == 1:
        return owners[0], "linked"
    return None, "none"


def apply_user_email_update(user, old_email, new_email):
    if CustomUser.objects.filter(
        Q(email__iexact=new_email) | Q(username__iexact=new_email),
    ).exclude(pk=user.pk).exists():
        raise EmailChangeError(
            "conflicting_user", "Another user already uses this email/username",
            status=409,
        )
    fields = {"email": new_email}
    if (user.username or "").lower() == (user.email or "").lower():
        fields["username"] = new_email
    CustomUser.objects.filter(pk=user.pk).update(**fields)
    EmailAddress.objects.filter(user=user, email__iexact=old_email).delete()
    EmailAddress.objects.update_or_create(
        user=user, email=new_email,
        defaults={"primary": True, "verified": True},
    )


def resync_relay(old_snapshot, registration, enrollment):
    """Move Relay list membership from the old email to the new one."""
    from course_management.datamailer.sync.membership_removals import (
        remove_registration_from_datamailer,
    )
    from course_management.datamailer.sync.memberships import (
        sync_enrollment_to_datamailer,
    )
    from course_management.relay.registration import (
        sync_registration_to_approved_list,
        sync_registration_to_relay,
    )

    remove_registration_from_datamailer(old_snapshot)
    sync_registration_to_relay(registration)
    if registration.status == CourseRegistration.Status.APPROVED:
        sync_registration_to_approved_list(registration)
    if enrollment is not None:
        sync_enrollment_to_datamailer(enrollment)


@transaction.atomic
def change_registration_email(
    registration, new_email, *, update_user=True, apply=True, sync=True,
):
    new_email = clean_new_email(new_email)
    registration = CourseRegistration.objects.select_for_update(
        of=("self",),
    ).select_related("user", "course", "campaign").get(pk=registration.pk)
    old_email = registration.email_normalized
    if new_email == old_email:
        raise EmailChangeError(
            "unchanged", "New email equals current email", status=409,
        )
    duplicate = CourseRegistration.objects.filter(
        campaign=registration.campaign, email_normalized=new_email,
    ).exclude(pk=registration.pk).first()
    if duplicate:
        raise EmailChangeError(
            "duplicate_registration",
            f"Registration {duplicate.pk} already uses {new_email} in this "
            "campaign",
            status=409,
        )
    user, action = plan_user(registration, new_email, update_user)
    result = EmailChangeResult(
        registration=registration, old_email=old_email, new_email=new_email,
        applied=apply, user_id=user.pk if user else None, user_action=action,
    )
    if not apply:
        return result

    old_snapshot = copy.copy(registration)
    if action == "email_updated":
        apply_user_email_update(user, old_email, new_email)
    update = {"email": new_email, "email_normalized": new_email}
    if action == "linked":
        update["user"] = user
    CourseRegistration.objects.filter(pk=registration.pk).update(**update)
    registration.refresh_from_db()

    enrollment = None
    if (registration.status == CourseRegistration.Status.APPROVED
            and registration.course_id is not None and user is not None):
        existed = Enrollment.objects.filter(
            student=user, course_id=registration.course_id,
        ).exists()
        enrollment = reconcile_approved_registration(registration, silent=True)
        result.enrollment_created = enrollment is not None and not existed
    if enrollment is not None:
        result.enrollment_id = enrollment.pk
    result.registration = registration
    if sync:
        sync_enrollment = enrollment if result.enrollment_created else None
        transaction.on_commit(
            partial(resync_relay, old_snapshot, registration, sync_enrollment)
        )
    return result
