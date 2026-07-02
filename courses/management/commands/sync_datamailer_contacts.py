from dataclasses import dataclass

import requests
from django.core.management.base import BaseCommand, CommandError

from accounts.models import CustomUser
from course_management.datamailer.client import (
    DatamailerClient,
    DatamailerConfig,
)
from course_management.datamailer.payloads.base import (
    contact_payload_for_user,
)


@dataclass(frozen=True)
class ContactBatchSyncData:
    config: DatamailerConfig
    client: DatamailerClient
    index: int
    batch: list


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
    users = contact_queryset(active_only=active_only)
    for user in users:
        payload = contact_payload_for_user(user)
        if payload is not None:
            payloads.append(payload)
    return payloads


def batches(items, batch_size):
    current_batch = []
    for item in items:
        current_batch.append(item)
        if len(current_batch) == batch_size:
            yield current_batch
            current_batch = []
    if current_batch:
        yield current_batch


def contact_batches(*, active_only, batch_size):
    payloads = contact_payloads(active_only=active_only)
    if not payloads:
        return [], 0
    contact_batch_iterator = batches(payloads, batch_size)
    contact_batch_list = list(contact_batch_iterator)
    total_contacts = len(payloads)
    return contact_batch_list, total_contacts


def write_batch_summary(write_line, contact_batch_list, total_contacts):
    write_line(
        f"Prepared {len(contact_batch_list)} contact batch(es), "
        f"{total_contacts} contact(s)."
    )


def write_dry_run(write_line, contact_batch_list):
    for index, batch in enumerate(contact_batch_list, start=1):
        write_line(f"batch {index}: {len(batch)} contact(s)")


def contact_import_payload(data):
    return {
        "audience": data.config.audience,
        "client": data.config.client,
        "idempotency_key": f"cmp-contact-bootstrap:{data.index}",
        "contacts": data.batch,
    }


def sync_contact_batch(data):
    payload = contact_import_payload(data)
    try:
        return data.client.contacts.bulk_import_contacts(payload)
    except requests.RequestException as exc:
        if data.config.strict:
            raise
        raise CommandError(
            "Datamailer contact sync failed for batch "
            f"{data.index}: {exc}"
        ) from exc


def sync_contact_batches(config, contact_batch_list, write_line):
    client = DatamailerClient(config)
    for index, batch in enumerate(contact_batch_list, start=1):
        sync_data = ContactBatchSyncData(
            config=config,
            client=client,
            index=index,
            batch=batch,
        )
        response = sync_contact_batch(sync_data)
        write_sync_result(write_line, index, batch, response)


def write_sync_result(write_line, index, batch, response):
    summary = sync_count_summary(response)
    suffix = ""
    if summary:
        suffix = f"; {summary}"
    write_line(f"Synced batch {index}: {len(batch)} contact(s){suffix}")


def sync_count_summary(response):
    if response:
        counts = response.get("counts", {})
    else:
        counts = {}
    summary_parts = []
    for key in (
        "created",
        "updated",
        "unchanged",
        "skipped",
        "invalid",
    ):
        if key in counts:
            summary_part = f"{key}={counts[key]}"
            summary_parts.append(summary_part)
    return ", ".join(summary_parts)


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
        contact_batch_list, total_contacts = contact_batches(
            active_only=options["active_only"],
            batch_size=batch_size,
        )
        if not contact_batch_list:
            self.stdout.write("No Datamailer contacts to sync.")
            return

        write_batch_summary(
            self.stdout.write,
            contact_batch_list,
            total_contacts,
        )

        if options["dry_run"]:
            write_dry_run(self.stdout.write, contact_batch_list)
            return

        sync_contact_batches(config, contact_batch_list, self.stdout.write)

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
