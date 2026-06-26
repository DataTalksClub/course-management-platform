import requests
from django.core.management.base import BaseCommand, CommandError

from accounts.models import CustomUser
from course_management.datamailer import (
    DatamailerClient,
    DatamailerConfig,
    contact_payload_for_user,
)


def contact_queryset(*, active_only=False):
    queryset = (
        CustomUser.objects.exclude(email__isnull=True)
        .exclude(email="")
        .order_by("pk")
    )
    if active_only:
        queryset = queryset.filter(is_active=True)
    return queryset


def contact_payloads(*, active_only=False):
    payloads = []
    for user in contact_queryset(active_only=active_only):
        payload = contact_payload_for_user(user)
        if payload is not None:
            payloads.append(payload)
    return payloads


def batches(items, batch_size):
    for index in range(0, len(items), batch_size):
        yield items[index : index + batch_size]


class Command(BaseCommand):
    help = "Backfill Datamailer contacts from CMP users."

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=500,
            help="Number of contacts to send per Datamailer import request.",
        )
        parser.add_argument(
            "--active-only",
            action="store_true",
            help="Only include active CMP users.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print planned imports without calling Datamailer.",
        )

    def handle(self, *args, **options):
        config = DatamailerConfig.from_settings()
        if config is None:
            raise CommandError(
                "Datamailer is not configured. Set DATAMAILER_URL, "
                "DATAMAILER_API_KEY, DATAMAILER_CLIENT, and DATAMAILER_AUDIENCE."
            )

        batch_size = options["batch_size"]
        if batch_size < 1:
            raise CommandError("--batch-size must be greater than zero.")

        payloads = contact_payloads(active_only=options["active_only"])
        if not payloads:
            self.stdout.write("No Datamailer contacts to sync.")
            return

        contact_batches = list(batches(payloads, batch_size))
        self.stdout.write(
            f"Prepared {len(contact_batches)} contact batch(es), "
            f"{len(payloads)} contact(s)."
        )

        if options["dry_run"]:
            for index, batch in enumerate(contact_batches, start=1):
                self.stdout.write(f"batch {index}: {len(batch)} contact(s)")
            return

        client = DatamailerClient(config)
        for index, batch in enumerate(contact_batches, start=1):
            payload = {
                "audience": config.audience,
                "client": config.client,
                "idempotency_key": f"cmp-contact-bootstrap:{index}",
                "contacts": batch,
            }
            try:
                response = client.bulk_import_contacts(payload)
            except requests.RequestException as exc:
                if config.strict:
                    raise
                raise CommandError(
                    f"Datamailer contact sync failed for batch {index}: {exc}"
                ) from exc

            counts = response.get("counts", {}) if response else {}
            summary = ", ".join(
                f"{key}={counts[key]}"
                for key in (
                    "created",
                    "updated",
                    "unchanged",
                    "skipped",
                    "invalid",
                )
                if key in counts
            )
            suffix = f"; {summary}" if summary else ""
            self.stdout.write(
                f"Synced batch {index}: {len(batch)} contact(s){suffix}"
            )
