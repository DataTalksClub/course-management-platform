from courses.models.course import Enrollment


def persist_certificate_updates(enrollments_to_update):
    if enrollments_to_update:
        enrollments = enrollments_to_update.values()
        Enrollment.objects.bulk_update(
            enrollments,
            ["certificate_url"],
        )
