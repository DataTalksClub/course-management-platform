from django.core.management.base import BaseCommand
from django.utils import timezone

from course_management.datamailer_outbox import datamailer_outbox_status_summary
from data.models import DatamailerOutboxStatus


class Command(BaseCommand):
    help = "Show Datamailer outbox health and recent dispatcher state."

    def write_event_counts(self, counts):
        for status in DatamailerOutboxStatus.values:
            self.stdout.write(f"{status}: {counts.get(status, 0)}")

    def write_due_status(self, summary):
        self.stdout.write(f"due: {summary['due_count']}")
        oldest_due = summary["oldest_due"]
        if oldest_due is None:
            self.stdout.write("oldest_due_age: none")
        else:
            now = timezone.now()
            age = now - oldest_due.next_attempt_at
            total_seconds = age.total_seconds()
            age_seconds = int(total_seconds)
            self.stdout.write(
                f"oldest_due_age: {age_seconds} seconds "
                f"({oldest_due.event_id})"
            )

    def write_last_successful_run(self, summary):
        last_successful_run = summary["last_successful_run"]
        if last_successful_run is None:
            self.stdout.write("last_successful_run: none")
        else:
            self.stdout.write(
                "last_successful_run: "
                f"{last_successful_run.finished_at or last_successful_run.started_at} "
                f"processed={last_successful_run.processed_count}"
            )

    def write_last_run(self, summary):
        last_run = summary["last_run"]
        if last_run is None:
            self.stdout.write("last_run: none")
        else:
            self.stdout.write(
                f"last_run: {last_run.status} "
                f"processed={last_run.processed_count} "
                f"retrying={last_run.retrying_count} "
                f"failed={last_run.failed_count}"
            )
            if last_run.last_error:
                self.stdout.write(f"last_run_error: {last_run.last_error}")

    def write_last_datamailer_error(self, summary):
        last_error_event = summary["last_error_event"]
        if last_error_event is None:
            self.stdout.write("last_datamailer_error: none")
        else:
            self.stdout.write(
                "last_datamailer_error: "
                f"{last_error_event.event_id} "
                f"{last_error_event.status} "
                f"{last_error_event.last_error}"
            )

    def handle(self, *args, **options):
        summary = datamailer_outbox_status_summary()
        self.stdout.write("Datamailer outbox status")
        self.write_event_counts(summary["event_counts"])
        self.write_due_status(summary)
        self.write_last_successful_run(summary)
        self.write_last_run(summary)
        self.write_last_datamailer_error(summary)
