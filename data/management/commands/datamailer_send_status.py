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
            summary_json = json.dumps(
                summary, default=str, indent=2, sort_keys=True
            )
            self.stdout.write(summary_json)
            return

        self._print_totals(summary["totals"])
        self._print_group("by_status", summary["by_status"])
        self._print_group("by_type", summary["by_type"])
        self._print_group("by_category", summary["by_category"])
        self._print_recent_failures(summary["recent_failures"])

    def _print_totals(self, totals):
        self.stdout.write("Datamailer send status")
        self.stdout.write(f"total_sends: {totals['total']}")
        self.stdout.write(f"succeeded: {totals['succeeded']}")
        self.stdout.write(f"failed: {totals['failed']}")
        last_send_at = totals["last_send_at"] or "none"
        self.stdout.write(f"last_send_at: {last_send_at}")
        self.stdout.write(f"intended: {totals['intended_count']}")
        self.stdout.write(f"enqueued: {totals['enqueued_count']}")
        self.stdout.write(f"skipped: {totals['skipped_count']}")
        self.stdout.write(
            f"idempotent_replays: {totals['idempotent_replay_count']}"
        )

    def _print_recent_failures(self, recent_failures):
        self.stdout.write("recent_failures:")
        if not recent_failures:
            self.stdout.write("  none")
            return
        for item in recent_failures:
            error = item["error"] or "-"
            self.stdout.write(
                "  "
                f"{item['occurred_at']} {item['send_type']} "
                f"{item['idempotency_key']} {error}"
            )

    def _print_group(self, label, rows):
        self.stdout.write(f"{label}:")
        if not rows:
            self.stdout.write("  none")
            return
        for row in rows:
            key = row["key"] or "-"
            self.stdout.write(
                "  "
                f"{key}: {row['count']} "
                f"enqueued={row['enqueued_count']} "
                f"skipped={row['skipped_count']}"
            )


def datamailer_send_audit_summary(*, limit):
    totals = send_audit_totals()
    by_status = grouped_counts("status")
    by_type = grouped_counts("send_type")
    by_category = grouped_counts("category_tag")
    recent_failures = recent_failed_sends(limit)

    return {
        "totals": totals,
        "by_status": by_status,
        "by_type": by_type,
        "by_category": by_category,
        "recent_failures": recent_failures,
    }


def send_audit_aggregate():
    total_count = Count("id")
    intended_count_sum = Sum("intended_count")
    enqueued_count_sum = Sum("enqueued_count")
    skipped_count_sum = Sum("skipped_count")
    idempotent_replay_count_sum = Sum("idempotent_replay_count")
    last_send_at = Max("occurred_at")

    return DatamailerSendAudit.objects.aggregate(
        total=total_count,
        intended_count=intended_count_sum,
        enqueued_count=enqueued_count_sum,
        skipped_count=skipped_count_sum,
        idempotent_replay_count=idempotent_replay_count_sum,
        last_send_at=last_send_at,
    )


def send_status_count(status):
    return DatamailerSendAudit.objects.filter(status=status).count()


def send_audit_totals():
    aggregate = send_audit_aggregate()
    total = aggregate["total"] or 0
    intended_count = aggregate["intended_count"] or 0
    enqueued_count = aggregate["enqueued_count"] or 0
    skipped_count = aggregate["skipped_count"] or 0
    idempotent_replay_count = aggregate["idempotent_replay_count"] or 0

    return {
        "total": total,
        "succeeded": send_status_count("succeeded"),
        "failed": send_status_count("failed"),
        "last_send_at": aggregate["last_send_at"],
        "intended_count": intended_count,
        "enqueued_count": enqueued_count,
        "skipped_count": skipped_count,
        "idempotent_replay_count": idempotent_replay_count,
    }


def recent_failed_sends(limit):
    failed_sends = []
    failed_audits = DatamailerSendAudit.objects.filter(status="failed")[
        :limit
    ]
    for item in failed_audits:
        failed_send = {
            "occurred_at": item.occurred_at,
            "send_type": item.send_type,
            "idempotency_key": item.idempotency_key,
            "error": item.error,
        }
        failed_sends.append(failed_send)
    return failed_sends


def grouped_counts(field):
    counts = []
    group_count = Count("id")
    enqueued_count_sum = Sum("enqueued_count")
    skipped_count_sum = Sum("skipped_count")
    rows = (
        DatamailerSendAudit.objects.values(field)
        .annotate(
            count=group_count,
            enqueued_count=enqueued_count_sum,
            skipped_count=skipped_count_sum,
        )
        .order_by(field)
    )
    for row in rows:
        count_record = {
            "key": row[field],
            "count": row["count"],
            "enqueued_count": row["enqueued_count"] or 0,
            "skipped_count": row["skipped_count"] or 0,
        }
        counts.append(count_record)
    return counts
