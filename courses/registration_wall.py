"""Registration wall: course-level access control for gated courses.

When ``Course.requires_registration_approval`` is on, the gated course
path (homework, projects, self-enrollment) is only available to users
with an **approved** ``CourseRegistration``. Everyone else can still
audit public materials (e.g. GitHub) but cannot submit or enroll.

The wall flag lives on ``Course`` (not ``RegistrationCampaign``)
because enforcement is per gated course path, while a campaign is only
a landing page that may point at different editions over time.
"""

from courses.models.course import CourseRegistration, Enrollment


class RegistrationWallBlocked(Exception):
    """Raised when the registration wall blocks a gated-path write."""


def course_has_registration_wall(course) -> bool:
    return bool(
        course is not None
        and getattr(course, "requires_registration_approval", False)
    )


def normalized_wall_email(user) -> str:
    email = getattr(user, "email", "") or ""
    return email.strip().lower()


def approved_registration_for_user(course, user):
    """Return the approved registration for this course+user, if any."""
    if not user.is_authenticated:
        return None
    email_normalized = normalized_wall_email(user)
    if not email_normalized:
        return None
    return (
        CourseRegistration.objects.filter(
            course=course,
            email_normalized=email_normalized,
            status=CourseRegistration.Status.APPROVED,
        )
        .order_by("-updated_at")
        .first()
    )


def registration_wall_status_for_user(course, user) -> str | None:
    """Pending/rejected/approved status for wall UX, or None if never applied."""
    if not user.is_authenticated:
        return None
    email_normalized = normalized_wall_email(user)
    if not email_normalized:
        return None
    registration = (
        CourseRegistration.objects.filter(
            course=course,
            email_normalized=email_normalized,
        )
        .order_by("-updated_at")
        .first()
    )
    if registration is None:
        return None
    return registration.status


def registration_wall_blocks_user(course, user) -> bool:
    """True when the wall flag is on and this user may not use the gated path."""
    if not course_has_registration_wall(course):
        return False
    if getattr(user, "is_staff", False):
        return False
    return approved_registration_for_user(course, user) is None


def get_or_create_enrollment_for_content(user, course):
    """Enrollment helper for homework/project content views.

    Returns ``(enrollment, blocked)``. When the registration wall
    blocks the user, no enrollment is created and ``blocked`` is True.
    Otherwise behaves like ``Enrollment.objects.get_or_create`` and
    ``blocked`` is False.
    """
    if registration_wall_blocks_user(course, user):
        return None, True
    enrollment, _ = Enrollment.objects.get_or_create(
        student=user,
        course=course,
    )
    return enrollment, False


def approve_registration(registration):
    """Mark a registration approved and enroll the linked/matching user.

    Returns the ``Enrollment`` when a user account could be matched,
    otherwise ``None`` (the applicant enrolls on next login-gated
    access once their account email matches).
    """
    from accounts.models import CustomUser

    registration.status = CourseRegistration.Status.APPROVED
    registration.save(update_fields=["status", "updated_at"])
    user = registration.user
    if user is None and registration.email_normalized:
        user = CustomUser.objects.filter(
            email__iexact=registration.email_normalized
        ).first()
        if user is not None:
            registration.user = user
            registration.save(update_fields=["user", "updated_at"])
    if user is None or registration.course_id is None:
        return None
    enrollment, _ = Enrollment.objects.get_or_create(
        student=user,
        course_id=registration.course_id,
    )
    return enrollment
