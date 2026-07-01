from dataclasses import dataclass

from courses.models.course import Enrollment, User

from api.views.enrollment_certificate_delivery import (
    persist_certificate_updates,
    queue_certificate_notifications,
)
from api.views.enrollment_certificate_validation import (
    validate_certificate_update_items,
)


@dataclass
class CertificateApplyResult:
    enrollment: Enrollment | None = None
    notify: bool = False
    updated: dict | None = None
    error: dict | None = None


@dataclass
class CertificateApplyBatch:
    enrollments_to_update: dict
    enrollments_to_notify: dict
    updated: list
    errors: list

    def record(self, result):
        if result.error:
            self.errors.append(result.error)
            return

        enrollment = result.enrollment
        self.enrollments_to_update[enrollment.id] = enrollment
        if result.notify:
            self.enrollments_to_notify[enrollment.id] = enrollment
        self.updated.append(result.updated)


@dataclass(frozen=True)
class CertificateUpdateLookups:
    course_slug: str
    users_by_email: dict
    enrollments_by_email: dict


def process_certificate_updates(
    course,
    course_slug,
    certificate_updates,
    notification_sender,
):
    valid_updates, errors = validate_certificate_update_items(
        certificate_updates
    )

    lookups = certificate_update_lookups(
        course,
        course_slug,
        valid_updates,
    )
    apply_batch = apply_certificate_updates(
        valid_updates,
        lookups,
    )
    errors.extend(apply_batch.errors)

    persist_certificate_updates(apply_batch.enrollments_to_update)
    queue_certificate_notifications(
        apply_batch.enrollments_to_notify,
        notification_sender,
    )

    return apply_batch.updated, errors


def certificate_update_lookups(course, course_slug, valid_updates):
    emails = []
    for update in valid_updates:
        emails.append(update["email"])

    users_by_email = {}
    users = User.objects.filter(email__in=emails)
    for user in users:
        users_by_email[user.email] = user

    enrollments_by_email = {}
    enrollments = Enrollment.objects.filter(
        course=course,
        student__email__in=emails,
    ).select_related("student")
    for enrollment in enrollments:
        enrollments_by_email[enrollment.student.email] = enrollment

    lookups = CertificateUpdateLookups(
        course_slug=course_slug,
        users_by_email=users_by_email,
        enrollments_by_email=enrollments_by_email,
    )
    return lookups


def apply_certificate_updates(valid_updates, lookups):
    batch = CertificateApplyBatch(
        enrollments_to_update={},
        enrollments_to_notify={},
        updated=[],
        errors=[],
    )

    for update in valid_updates:
        result = apply_certificate_update(
            update,
            lookups,
        )
        batch.record(result)

    return batch


def apply_certificate_update(update, lookups):
    email = update["email"]
    certificate_path = update["certificate_path"]

    if email not in lookups.users_by_email:
        error = user_not_found_error(update)
        return CertificateApplyResult(error=error)

    enrollment = lookups.enrollments_by_email.get(email)
    if enrollment is None:
        error = not_enrolled_error(update, lookups.course_slug)
        return CertificateApplyResult(error=error)

    notify = should_notify_certificate_available(
        enrollment,
        certificate_path,
    )
    enrollment.certificate_url = certificate_path
    updated = certificate_update_result(update, enrollment)
    return CertificateApplyResult(
        enrollment=enrollment,
        notify=notify,
        updated=updated,
    )


def user_not_found_error(update):
    email = update["email"]
    return certificate_update_error(
        update,
        "user_not_found",
        f"User with email {email} not found",
    )


def not_enrolled_error(update, course_slug):
    email = update["email"]
    return certificate_update_error(
        update,
        "not_enrolled",
        f"User {email} is not enrolled in course {course_slug}",
    )


def certificate_update_error(update, code, error):
    return {
        "index": update["index"],
        "email": update["email"],
        "code": code,
        "error": error,
    }


def should_notify_certificate_available(enrollment, certificate_path):
    existing_certificate_url = enrollment.certificate_url or ""
    stripped_existing_certificate_url = existing_certificate_url.strip()
    stripped_certificate_path = certificate_path.strip()
    had_certificate = bool(stripped_existing_certificate_url)
    has_new_certificate = bool(stripped_certificate_path)
    return not had_certificate and has_new_certificate


def certificate_update_result(update, enrollment):
    return {
        "index": update["index"],
        "email": update["email"],
        "enrollment_id": enrollment.id,
        "certificate_url": update["certificate_path"],
    }
