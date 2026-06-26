from django.core.management.base import BaseCommand
from django.db.models import Count, Max, Sum

from data.models import DatamailerContactEvent


class Command(BaseCommand):
    help = "Show Datamailer callback health from stored webhook events."

    def handle(self, *args, **options):
        aggregate = DatamailerContactEvent.objects.aggregate(
            total=Count("id"),
            duplicates=Sum("duplicate_count"),
            last_created_at=Max("created_at"),
            last_seen_at=Max("last_seen_at"),
        )
        duplicates = aggregate["duplicates"] or 0

        self.stdout.write("Datamailer callback status")
        self.stdout.write(f"total_events: {aggregate['total']}")
        self.stdout.write(f"duplicate_callbacks: {duplicates}")
        self.stdout.write(
            f"last_created_at: {aggregate['last_created_at'] or 'none'}"
        )
        self.stdout.write(f"last_seen_at: {aggregate['last_seen_at'] or 'none'}")

        event_counts = (
            DatamailerContactEvent.objects.values("event_type")
            .annotate(count=Count("id"), duplicates=Sum("duplicate_count"))
            .order_by("event_type")
        )
        if not event_counts:
            self.stdout.write("event_types: none")
            return

        self.stdout.write("event_types:")
        for row in event_counts:
            self.stdout.write(
                f"{row['event_type']}: {row['count']} "
                f"(duplicates={row['duplicates'] or 0})"
            )
