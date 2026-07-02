from dataclasses import dataclass

import requests
from django.core.management.base import CommandError

from course_management.datamailer.client import (
    DatamailerClient,
    DatamailerConfig,
)
from course_management.datamailer.recipient_list_drift import member_drift


@dataclass(frozen=True)
class AuditRunData:
    client: DatamailerClient
    config: DatamailerConfig
    batches: dict
    limit: int
    repair: bool


@dataclass(frozen=True)
class AuditListData:
    client: DatamailerClient
    config: DatamailerConfig
    list_key: str
    payload: dict
    limit: int
    repair: bool


@dataclass(frozen=True)
class DriftReportData:
    list_key: str
    expected: dict
    actual: dict
    drift: dict


def audit_batches_against_datamailer(data, write_line):
    drift_count = 0
    for list_key, payload in data.batches.items():
        list_data = AuditListData(
            client=data.client,
            config=data.config,
            list_key=list_key,
            payload=payload,
            limit=data.limit,
            repair=data.repair,
        )
        drift = audit_list(list_data, write_line)
        if drift["has_drift"]:
            drift_count += 1
    return drift_count


def audit_list(data, write_line):
    response = list_members(data)
    ensure_complete_response(response, data.list_key, data.limit)
    drift_data = member_drift(data.payload, response)
    report_data = DriftReportData(
        list_key=data.list_key,
        expected=drift_data.expected,
        actual=drift_data.actual,
        drift=drift_data.drift,
    )
    print_drift(write_line, report_data)

    if data.repair and drift_data.drift["has_drift"]:
        repair_list(data, write_line)
    return drift_data.drift


def list_members(data):
    try:
        return data.client.recipient_lists.recipient_list_members(
            data.list_key,
            include_removed=False,
            limit=data.limit,
        )
    except requests.RequestException as exc:
        if data.config.strict:
            raise
        raise CommandError(
            f"Datamailer member listing failed for {data.list_key}: {exc}"
        ) from exc


def ensure_complete_response(response, list_key, limit):
    if (response or {}).get("has_more"):
        raise CommandError(
            f"Datamailer returned more than {limit} active members for {list_key}; "
            "rerun with a narrower course/item filter."
        )


def repair_list(data, write_line):
    try:
        repair_response = data.client.recipient_lists.reconcile_recipient_list_members(
            data.list_key,
            data.payload,
        )
    except requests.RequestException as exc:
        if data.config.strict:
            raise
        raise CommandError(
            f"Datamailer repair failed for {data.list_key}: {exc}"
        ) from exc
    write_line(
        "Repaired "
        f"{data.list_key}: upserted={repair_response.get('upsert_count', 0)} "
        f"removed={repair_response.get('removed_count', 0)}"
    )


def print_drift(write_line, data):
    write_line(
        f"Audited {data.list_key}: expected={len(data.expected)} "
        f"actual={len(data.actual)} missing={len(data.drift['missing'])} "
        f"unexpected={len(data.drift['unexpected'])} "
        f"email_mismatches={len(data.drift['email_mismatches'])} "
        f"metadata_mismatches={len(data.drift['metadata_mismatches'])}"
    )
    for label in (
        "missing",
        "unexpected",
        "email_mismatches",
        "metadata_mismatches",
    ):
        if data.drift[label]:
            write_line(f"{label}: {', '.join(data.drift[label])}")
