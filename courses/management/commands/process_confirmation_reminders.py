from django.core.management.base import BaseCommand
from course_management.relay.confirmation_reminders import process_confirmation_reminders


class Command(BaseCommand):
    help = "Send due confirmation reminders and delete expired unconfirmed registrations with a final reminder."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Print counts without sending or changing data.")
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        result = process_confirmation_reminders(dry_run=options["dry_run"], limit=options["limit"])
        self.stdout.write(f"dry_run={options['dry_run']} reminded={result['reminded']} deleted={result['deleted']} failed={result['failed']}")
