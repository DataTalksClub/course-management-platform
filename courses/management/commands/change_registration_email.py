"""Change a CourseRegistration email without sending mail (dry-run default)."""

import json

from django.core.management.base import BaseCommand, CommandError

from courses.models import CourseRegistration
from courses.registration_email_change import (
    EmailChangeError,
    change_registration_email,
)


class Command(BaseCommand):
    help = "Change a registration email, link/update user, no mail"

    def add_arguments(self, parser):
        parser.add_argument("registration_id", type=int)
        parser.add_argument("new_email")
        parser.add_argument("--no-update-user", action="store_true")
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        registration = CourseRegistration.objects.filter(
            pk=options["registration_id"],
        ).first()
        if registration is None:
            raise CommandError("registration not found")
        try:
            result = change_registration_email(
                registration,
                options["new_email"],
                update_user=not options["no_update_user"],
                apply=options["apply"],
            )
        except EmailChangeError as exc:
            raise CommandError(f"{exc.code}: {exc.message}")
        self.stdout.write(json.dumps({
            "applied": result.applied,
            "old_email": result.old_email,
            "new_email": result.new_email,
            "user_id": result.user_id,
            "user_action": result.user_action,
            "enrollment_id": result.enrollment_id,
            "enrollment_created": result.enrollment_created,
        }, sort_keys=True))
