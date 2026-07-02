from functools import partial

from django.db import transaction

from courses.models.course import Enrollment


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
    for enrollment in enrollments_to_notify.values():
        send_notification = partial(notification_sender, enrollment)
        transaction.on_commit(send_notification)
