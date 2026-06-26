import json

from django.core.management.base import BaseCommand
from django.db.models import Count, Max, Sum

from data.models import DatamailerSendAudit


class Command(BaseCommand):
    help = "Show Datamailer send audit counts recorded by CMP."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=5,
            help="Number of recent failed sends to show.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Print the summary as JSON.",
        )

    def handle(self, *args, **options):
        summary = datamailer_send_audit_summary(limit=options["limit"])
        if options["json"]:
            self.stdout.write(
                json.dumps(summary, default=str, indent=2, sort_keys=True)
            )
            return

        totals = summary["totals"]
        self.stdout.write("Datamailer send status")
        self.stdout.write(f"total_sends: {totals['total']}")
        self.stdout.write(f"succeeded: {totals['succeeded']}")
        self.stdout.write(f"failed: {totals['failed']}")
        self.stdout.write(f"last_send_at: {totals['last_send_at'] or 'none'}")
        self.stdout.write(f"intended: {totals['intended_count']}")
        self.stdout.write(f"enqueued: {totals['enqueued_count']}")
        self.stdout.write(f"skipped: {totals['skipped_count']}")
        self.stdout.write(
            f"idempotent_replays: {totals['idempotent_replay_count']}"
        )

        self._print_group("by_status", summary["by_status"])
        self._print_group("by_type", summary["by_type"])
        self._print_group("by_category", summary["by_category"])

        self.stdout.write("recent_failures:")
        if not summary["recent_failures"]:
            self.stdout.write("  none")
            return
        for item in summary["recent_failures"]:
            self.stdout.write(
                "  "
                f"{item['occurred_at']} {item['send_type']} "
                f"{item['idempotency_key']} {item['error'] or '-'}"
            )

    def _print_group(self, label, rows):
        self.stdout.write(f"{label}:")
        if not rows:
            self.stdout.write("  none")
            return
        for row in rows:
            self.stdout.write(
                "  "
                f"{row['key'] or '-'}: {row['count']} "
                f"enqueued={row['enqueued_count']} "
                f"skipped={row['skipped_count']}"
            )


def datamailer_send_audit_summary(*, limit):
    aggregate = DatamailerSendAudit.objects.aggregate(
        total=Count("id"),
        intended_count=Sum("intended_count"),
        enqueued_count=Sum("enqueued_count"),
        skipped_count=Sum("skipped_count"),
        idempotent_replay_count=Sum("idempotent_replay_count"),
        last_send_at=Max("occurred_at"),
    )
    succeeded = DatamailerSendAudit.objects.filter(status="succeeded").count()
    failed = DatamailerSendAudit.objects.filter(status="failed").count()

    return {
        "totals": {
            "total": aggregate["total"] or 0,
            "succeeded": succeeded,
            "failed": failed,
            "last_send_at": aggregate["last_send_at"],
            "intended_count": aggregate["intended_count"] or 0,
            "enqueued_count": aggregate["enqueued_count"] or 0,
            "skipped_count": aggregate["skipped_count"] or 0,
            "idempotent_replay_count": aggregate["idempotent_replay_count"]
            or 0,
        },
        "by_status": grouped_counts("status"),
        "by_type": grouped_counts("send_type"),
        "by_category": grouped_counts("category_tag"),
        "recent_failures": [
            {
                "occurred_at": item.occurred_at,
                "send_type": item.send_type,
                "idempotency_key": item.idempotency_key,
                "error": item.error,
            }
            for item in DatamailerSendAudit.objects.filter(status="failed")[
                :limit
            ]
        ],
    }


def grouped_counts(field):
    return [
        {
            "key": row[field],
            "count": row["count"],
            "enqueued_count": row["enqueued_count"] or 0,
            "skipped_count": row["skipped_count"] or 0,
        }
        for row in DatamailerSendAudit.objects.values(field)
        .annotate(
            count=Count("id"),
            enqueued_count=Sum("enqueued_count"),
            skipped_count=Sum("skipped_count"),
        )
        .order_by(field)
    ]
