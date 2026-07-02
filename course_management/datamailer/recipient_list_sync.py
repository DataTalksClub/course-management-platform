from dataclasses import dataclass

from django.core.management.base import CommandError
import requests

from course_management.datamailer.client import (
    DatamailerClient,
    DatamailerConfig,
)
from course_management.datamailer.recipient_list_import_jobs import (
    ImportJobData,
    ImportJobOptions,
    create_import_job,
)


@dataclass(frozen=True)
class InlineSyncData:
    client: DatamailerClient
    config: DatamailerConfig
    list_key: str
    payload: dict
    reconcile: bool


@dataclass(frozen=True)
class RecipientListSyncData:
    client: DatamailerClient
    config: DatamailerConfig
    kind: str
    batches: dict
    reconcile: bool
    import_by_reference: bool
    import_options: ImportJobOptions


@dataclass(frozen=True)
class SyncResultData:
    list_key: str
    payload: dict
    response: dict | None


def sync_recipient_list_batches(data, write):
    for list_key, payload in data.batches.items():
        sync_recipient_list_batch(data, list_key, payload, write)


def sync_recipient_list_batch(data, list_key, payload, write):
    if data.import_by_reference:
        import_data = recipient_list_import_job_data(
            data,
            list_key,
            payload,
        )
        create_import_job(import_data, write)
        return

    result_data = sync_inline_recipient_list_batch(
        data,
        list_key,
        payload,
    )
    write_sync_result(result_data, write)


def recipient_list_import_job_data(data, list_key, payload):
    return ImportJobData(
        client=data.client,
        config=data.config,
        kind=data.kind,
        list_key=list_key,
        payload=payload,
        options=data.import_options,
    )


def sync_inline_recipient_list_batch(data, list_key, payload):
    inline_data = InlineSyncData(
        client=data.client,
        config=data.config,
        list_key=list_key,
        payload=payload,
        reconcile=data.reconcile,
    )
    response = sync_inline_batch(inline_data)
    result_data = SyncResultData(
        list_key=list_key,
        payload=payload,
        response=response,
    )
    return result_data


def sync_inline_batch(data):
    try:
        if data.reconcile:
            return data.client.recipient_lists.reconcile_recipient_list_members(
                data.list_key, data.payload
            )
        return data.client.recipient_lists.bulk_upsert_recipient_list_members(
            data.list_key, data.payload
        )
    except requests.RequestException as exc:
        if data.config.strict:
            raise
        raise CommandError(
            f"Datamailer sync failed for {data.list_key}: {exc}"
        ) from exc


def write_sync_result(data, write):
    active_count = active_member_count(data.response)
    if active_count is not None:
        suffix = f"; active={active_count}"
    else:
        suffix = ""
    member_count = len(data.payload["members"])
    write(f"Synced {data.list_key}: {member_count} member(s){suffix}")


def active_member_count(response):
    if not response:
        return None
    recipient_list = response.get("recipient_list", {})
    active_count = recipient_list.get("active_member_count")
    return active_count
