from dataclasses import dataclass

from django.db import transaction

from courses.models import Enrollment, User


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


def process_certificate_updates(
    course,
    course_slug,
    certificate_updates,
    notification_sender,
):
    valid_updates, errors = validate_certificate_update_items(
        certificate_updates
    )

    users_by_email, enrollments_by_email = certificate_update_lookups(
        course,
        valid_updates,
    )
    apply_batch = apply_certificate_updates(
        valid_updates,
        course_slug,
        users_by_email,
        enrollments_by_email,
    )
    errors.extend(apply_batch.errors)

    persist_certificate_updates(apply_batch.enrollments_to_update)
    queue_certificate_notifications(
        apply_batch.enrollments_to_notify,
        notification_sender,
    )

    return apply_batch.updated, errors


def validate_certificate_update_items(certificate_updates):
    valid_updates = []
    errors = []

    for index, update in enumerate(certificate_updates):
        valid_update, error = validate_certificate_update_item(index, update)
        if error:
            errors.append(error)
            continue
        valid_updates.append(valid_update)

    return valid_updates, errors


def validate_certificate_update_item(index, update):
    if not isinstance(update, dict):
        error = invalid_certificate_update_item_error(index)
        return None, error

    email = update.get("email")
    certificate_path = update.get("certificate_path")

    if not email or not certificate_path:
        error = missing_certificate_update_fields_error(index, email)
        return None, error

    valid_update = {
        "index": index,
        "email": email,
        "certificate_path": certificate_path,
    }
    return valid_update, None


def invalid_certificate_update_item_error(index):
    return {
        "index": index,
        "code": "invalid_item",
        "error": "Each certificate update must be an object",
    }


def missing_certificate_update_fields_error(index, email):
    return {
        "index": index,
        "email": email,
        "code": "missing_fields",
        "error": "Both email and certificate_path are required",
    }


def certificate_update_lookups(course, valid_updates):
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

    return users_by_email, enrollments_by_email


def apply_certificate_updates(
    valid_updates, course_slug, users_by_email, enrollments_by_email
):
    batch = CertificateApplyBatch(
        enrollments_to_update={},
        enrollments_to_notify={},
        updated=[],
        errors=[],
    )

    for update in valid_updates:
        result = apply_certificate_update(
            update,
            course_slug,
            users_by_email,
            enrollments_by_email,
        )
        batch.record(result)

    return batch


def apply_certificate_update(
    update,
    course_slug,
    users_by_email,
    enrollments_by_email,
):
    email = update["email"]
    certificate_path = update["certificate_path"]

    if email not in users_by_email:
        error = user_not_found_error(update)
        return CertificateApplyResult(error=error)

    enrollment = enrollments_by_email.get(email)
    if enrollment is None:
        error = not_enrolled_error(update, course_slug)
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


def persist_certificate_updates(enrollments_to_update):
    if enrollments_to_update:
        enrollments = enrollments_to_update.values()
        Enrollment.objects.bulk_update(
            enrollments,
            ["certificate_url"],
        )


def queue_certificate_notifications(
    enrollments_to_notify,
    notification_sender,
):
    notification_enrollments = enrollments_to_notify.values()
    for enrollment in notification_enrollments:

        def send_notification(enrollment=enrollment):
            notification_sender(enrollment)

        transaction.on_commit(send_notification)
