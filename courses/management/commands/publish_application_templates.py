from django.core.management.base import BaseCommand, CommandError

from course_management.relay.application_notifications import relay_request
from course_management.relay.application_templates import APPLICATION_TEMPLATES


class Command(BaseCommand):
    help = "Publish CMP application templates to the configured Relay client."

    def handle(self, *args, **options):
        for key, template in APPLICATION_TEMPLATES.items():
            path = f"/api/transactional/templates/{key}"
            try:
                relay_request("PUT", path, template)
                result = relay_request("POST", path + "/publish", {})
            except Exception as exc:
                raise CommandError(f"Relay template publish failed: {type(exc).__name__}") from None
            self.stdout.write(f"Published {key} version {result.get('latest_version')}")
