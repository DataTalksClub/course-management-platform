from django.core.management.base import BaseCommand

from courses.genmedia_approval import approve_pending_registrations


class Command(BaseCommand):
    help = (
        "Run the Production AI Agents evening bulk approval once. "
        "No-op outside the 20:00 Europe/Berlin hour or when the day "
        "already ran. Never sends emails."
    )

    def handle(self, *args, **options):
        result = approve_pending_registrations()
        if not result.ran:
            self.stdout.write(
                f"Genmedia approval not run ({result.reason})."
            )
            return
        self.stdout.write(
            f"Genmedia approval {result.day} ({result.reason}): "
            f"{result.approved} approved, {result.excluded} excluded."
        )
