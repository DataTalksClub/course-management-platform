"""Reconcile approved applications without replaying approval notifications."""

from allauth.account.models import EmailAddress
from django.db import transaction
from django.db.models import Q

from accounts.models import CustomUser
from courses.models import CourseRegistration, Enrollment
from courses.models.course import generate_random_name


def matching_registration_user(registration):
    """Keep explicit ownership; otherwise require one email owner.

    The account email is also used by the registration wall. Secondary
    allauth addresses must be verified before they can grant course access.
    Never choose an arbitrary account when legacy duplicate emails exist.
    """
    if registration.user_id:
        return registration.user
    email = registration.email_normalized
    if not email:
        return None
    verified_owners = EmailAddress.objects.filter(
        email__iexact=email, verified=True,
    ).values("user_id")
    users = list(CustomUser.objects.filter(
        Q(email__iexact=email) | Q(pk__in=verified_owners),
    ).distinct()[:2])
    return users[0] if len(users) == 1 else None


@transaction.atomic
def reconcile_approved_registration(registration, *, silent=False):
    """Link and enroll, returning None if no safe match exists.

    ``silent`` is for the operator backfill: bulk writes bypass all model
    signals, notification queues and external membership synchronization.
    Existing enrollments and approval timestamps are preserved.
    """
    registration = CourseRegistration.objects.select_for_update().get(
        pk=registration.pk,
    )
    if (registration.status != CourseRegistration.Status.APPROVED
            or registration.course_id is None):
        return None
    user = matching_registration_user(registration)
    if user is None:
        return None
    if registration.user_id is None:
        # Do not save the application: that would replay approved-list sync.
        CourseRegistration.objects.filter(pk=registration.pk).update(user=user)
    if silent:
        Enrollment.objects.bulk_create([
            Enrollment(
                student=user, course_id=registration.course_id,
                display_name=generate_random_name(),
            ),
        ], ignore_conflicts=True)
        return Enrollment.objects.get(
            student=user, course_id=registration.course_id,
        )
    enrollment, _ = Enrollment.objects.get_or_create(
        student=user, course_id=registration.course_id,
    )
    return enrollment


def reconcile_user_approved_registrations(user):
    """Run after authentication, including the first social signup/login."""
    emails = {email.strip().lower() for email in
              EmailAddress.objects.filter(user=user, verified=True)
              .values_list("email", flat=True) if email}
    if user.email:
        emails.add(user.email.strip().lower())
    registrations = CourseRegistration.objects.filter(
        status=CourseRegistration.Status.APPROVED,
        course__isnull=False,
    ).filter(Q(user=user) | Q(user__isnull=True, email_normalized__in=emails))
    for registration in registrations:
        # Resolve ownership again so duplicate emails cannot claim access.
        owner = matching_registration_user(registration)
        if owner is not None and owner.pk == user.pk:
            reconcile_approved_registration(registration)
