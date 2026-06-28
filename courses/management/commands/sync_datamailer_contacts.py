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
        config = self.get_datamailer_config()
        batch_size = self.validate_batch_size(options["batch_size"])
        contact_batches, total_contacts = self.get_contact_batches(
            active_only=options["active_only"],
            batch_size=batch_size,
        )
        if not contact_batches:
            self.stdout.write("No Datamailer contacts to sync.")
            return

        self.write_batch_summary(contact_batches, total_contacts)

        if options["dry_run"]:
            self.write_dry_run(contact_batches)
            return

        self.sync_contact_batches(config, contact_batches)

    def get_datamailer_config(self):
        config = DatamailerConfig.from_settings()
        if config is None:
            raise CommandError(
                "Datamailer is not configured. Set DATAMAILER_URL, "
                "DATAMAILER_API_KEY, DATAMAILER_CLIENT, and DATAMAILER_AUDIENCE."
            )
        return config

    def validate_batch_size(self, batch_size):
        if batch_size < 1:
            raise CommandError("--batch-size must be greater than zero.")
        return batch_size

    def get_contact_batches(self, *, active_only, batch_size):
        payloads = contact_payloads(active_only=active_only)
        if not payloads:
            return [], 0
        return list(batches(payloads, batch_size)), len(payloads)

    def write_batch_summary(self, contact_batches, total_contacts):
        self.stdout.write(
            f"Prepared {len(contact_batches)} contact batch(es), "
            f"{total_contacts} contact(s)."
        )

    def write_dry_run(self, contact_batches):
        for index, batch in enumerate(contact_batches, start=1):
            self.stdout.write(f"batch {index}: {len(batch)} contact(s)")

    def sync_contact_batches(self, config, contact_batches):
        client = DatamailerClient(config)
        for index, batch in enumerate(contact_batches, start=1):
            response = self.sync_contact_batch(config, client, index, batch)
            self.write_sync_result(index, batch, response)

    def sync_contact_batch(self, config, client, index, batch):
        payload = self.contact_import_payload(config, index, batch)
        try:
            return client.bulk_import_contacts(payload)
        except requests.RequestException as exc:
            if config.strict:
                raise
            raise CommandError(
                f"Datamailer contact sync failed for batch {index}: {exc}"
            ) from exc

    def contact_import_payload(self, config, index, batch):
        return {
            "audience": config.audience,
            "client": config.client,
            "idempotency_key": f"cmp-contact-bootstrap:{index}",
            "contacts": batch,
        }

    def write_sync_result(self, index, batch, response):
        summary = self.sync_count_summary(response)
        suffix = f"; {summary}" if summary else ""
        self.stdout.write(
            f"Synced batch {index}: {len(batch)} contact(s){suffix}"
        )

    def sync_count_summary(self, response):
        counts = response.get("counts", {}) if response else {}
        return ", ".join(
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
