from django.core.management.base import BaseCommand
from django.db.models import Count, Max, Sum

from data.models import DatamailerContactEvent


class Command(BaseCommand):
    help = "Show Datamailer callback health from stored webhook events."

    def handle(self, *args, **options):
        aggregate = callback_event_aggregate()
        event_counts = callback_event_counts()
        self._print_aggregate(aggregate)
        self._print_event_counts(event_counts)

    def _print_aggregate(self, aggregate):
        self.stdout.write("Datamailer callback status")
        self.stdout.write(f"total_events: {aggregate['total']}")
        duplicate_callbacks = aggregate["duplicates"] or 0
        self.stdout.write(f"duplicate_callbacks: {duplicate_callbacks}")
        last_created_at = aggregate["last_created_at"] or "none"
        self.stdout.write(f"last_created_at: {last_created_at}")
        last_seen_at = aggregate["last_seen_at"] or "none"
        self.stdout.write(f"last_seen_at: {last_seen_at}")

    def _print_event_counts(self, event_counts):
        if not event_counts:
            self.stdout.write("event_types: none")
            return

        self.stdout.write("event_types:")
        for row in event_counts:
            duplicates = row["duplicates"] or 0
            self.stdout.write(
                f"{row['event_type']}: {row['count']} "
                f"(duplicates={duplicates})"
            )


def callback_event_aggregate():
    total_count = Count("id")
    duplicate_count_sum = Sum("duplicate_count")
    last_created_at = Max("created_at")
    last_seen_at = Max("last_seen_at")
    return DatamailerContactEvent.objects.aggregate(
        total=total_count,
        duplicates=duplicate_count_sum,
        last_created_at=last_created_at,
        last_seen_at=last_seen_at,
    )


def callback_event_counts():
    event_count = Count("id")
    duplicate_count_sum = Sum("duplicate_count")
    return (
        DatamailerContactEvent.objects.values("event_type")
        .annotate(count=event_count, duplicates=duplicate_count_sum)
        .order_by("event_type")
    )
