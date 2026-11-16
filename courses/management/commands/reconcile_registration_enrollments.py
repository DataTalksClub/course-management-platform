"""Audit or silently repair approved registrations with existing accounts."""

import json
from collections import Counter

from django.core.management.base import BaseCommand
from django.db import transaction

from courses.models import CourseRegistration, Enrollment
from courses.registration_enrollment import (
    matching_registration_user,
    reconcile_approved_registration,
)


class Command(BaseCommand):
    help = "Repair approved enrollment links without mail or Relay writes (dry-run by default)"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--course-id", type=int)

    @transaction.atomic
    def handle(self, *args, **options):
        registrations = CourseRegistration.objects.filter(
            status=CourseRegistration.Status.APPROVED,
            course__isnull=False,
        ).select_related("user").order_by("pk")
        if options["course_id"]:
            registrations = registrations.filter(course_id=options["course_id"])
        counts = Counter()
        for registration in registrations:
            user = matching_registration_user(registration)
            course = registration.course_id
            if user is None:
                counts[f"{course}:unmatched"] += 1
                continue
            linked = registration.user_id is not None
            enrolled = Enrollment.objects.filter(
                student=user, course_id=course,
            ).exists()
            if linked and enrolled:
                counts[f"{course}:ok"] += 1
                continue
            if not linked:
                counts[f"{course}:link"] += 1
            if not enrolled:
                counts[f"{course}:enroll"] += 1
            if options["apply"]:
                reconcile_approved_registration(registration, silent=True)
        self.stdout.write(json.dumps({
            "apply": options["apply"], "counts": dict(sorted(counts.items())),
        }, sort_keys=True))
