from dataclasses import dataclass

import requests
from django.core.management.base import BaseCommand, CommandError

from course_management.datamailer import DatamailerClient, DatamailerConfig
from courses.management.commands.sync_datamailer_recipient_lists import (
    build_batches,
)

RECIPIENT_LIST_KINDS = [
    "registrations",
    "enrollments",
    "homework",
    "project",
    "project-passed",
    "graduates",
]


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


def add_recipient_list_filter_arguments(parser):
    parser.add_argument(
        "--course-slug",
        default="",
        help="Limit the audit to one course cohort slug.",
    )
    parser.add_argument(
        "--homework-slug",
        default="",
        help="Limit homework audit to one homework slug.",
    )
    parser.add_argument(
        "--project-slug",
        default="",
        help="Limit project audit to one project slug.",
    )


def add_audit_behavior_arguments(parser):
    parser.add_argument(
        "--limit",
        type=int,
        default=10000,
        help="Maximum Datamailer members to fetch per list.",
    )
    parser.add_argument(
        "--repair",
        action="store_true",
        help="Repair drift by reconciling Datamailer to the CMP snapshot.",
    )
    parser.add_argument(
        "--fail-on-drift",
        action="store_true",
        help="Exit with an error if any drift is detected.",
    )


class Command(BaseCommand):
    help = "Compare CMP recipient-list source data with Datamailer active members."

    def add_arguments(self, parser):
        parser.add_argument(
            "kind",
            choices=RECIPIENT_LIST_KINDS,
            help="CMP source to audit against Datamailer recipient lists.",
        )
        add_recipient_list_filter_arguments(parser)
        add_audit_behavior_arguments(parser)

    def handle(self, *args, **options):
        config = self._datamailer_config()
        self._validate_options(options)
        batches = self._audit_batches(options)
        if not batches:
            self.stdout.write(
                "No Datamailer recipient-list members to audit."
            )
            return

        client = DatamailerClient(config)
        audit_data = AuditRunData(
            client=client,
            config=config,
            batches=batches,
            limit=options["limit"],
            repair=options["repair"],
        )
        drift_count = self._audit_batches_against_datamailer(audit_data)
        self._write_audit_summary(batches, drift_count)
        self._fail_on_drift_if_requested(drift_count, options)

    def _datamailer_config(self):
        config = DatamailerConfig.from_settings()
        if config is None:
            raise CommandError(
                "Datamailer is not configured. Set DATAMAILER_URL, "
                "DATAMAILER_API_KEY, DATAMAILER_CLIENT, and DATAMAILER_AUDIENCE."
            )
        return config

    def _audit_batches(self, options):
        return build_batches(
            options["kind"],
            course_slug=options["course_slug"],
            homework_slug=options["homework_slug"],
            project_slug=options["project_slug"],
        )

    def _audit_batches_against_datamailer(self, data):
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
            drift = self._audit_list(list_data)
            if drift["has_drift"]:
                drift_count += 1
        return drift_count

    def _write_audit_summary(self, batches, drift_count):
        self.stdout.write(
            f"Audited {len(batches)} recipient list(s); "
            f"drifted={drift_count}."
        )

    def _fail_on_drift_if_requested(self, drift_count, options):
        if drift_count and options["fail_on_drift"]:
            raise CommandError(
                f"Datamailer recipient-list drift detected in {drift_count} list(s)."
            )

    def _validate_options(self, options):
        errors = option_validation_errors(options)
        for error in errors:
            raise CommandError(error)

    def _audit_list(self, data):
        response = self._list_members(data)
        self._ensure_complete_response(response, data.list_key, data.limit)
        expected, actual, drift = self._member_drift(data.payload, response)
        report_data = DriftReportData(
            list_key=data.list_key,
            expected=expected,
            actual=actual,
            drift=drift,
        )
        self._print_drift(report_data)

        if data.repair and drift["has_drift"]:
            self._repair_list(data)
        return drift

    def _list_members(self, data):
        try:
            return data.client.recipient_list_members(
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

    def _ensure_complete_response(self, response, list_key, limit):
        if (response or {}).get("has_more"):
            raise CommandError(
                f"Datamailer returned more than {limit} active members for {list_key}; "
                "rerun with a narrower course/item filter."
            )

    def _member_drift(self, payload, response):
        expected = expected_members(payload)
        actual = actual_members(response or {})
        drift = compare_members(expected, actual)
        return expected, actual, drift

    def _repair_list(self, data):
        try:
            repair_response = data.client.reconcile_recipient_list_members(
                data.list_key,
                data.payload,
            )
        except requests.RequestException as exc:
            if data.config.strict:
                raise
            raise CommandError(
                f"Datamailer repair failed for {data.list_key}: {exc}"
            ) from exc
        self.stdout.write(
            "Repaired "
            f"{data.list_key}: upserted={repair_response.get('upsert_count', 0)} "
            f"removed={repair_response.get('removed_count', 0)}"
        )

    def _print_drift(self, data):
        self.stdout.write(
            f"Audited {data.list_key}: expected={len(data.expected)} "
            f"actual={len(data.actual)} missing={len(data.drift['missing'])} "
            f"unexpected={len(data.drift['unexpected'])} "
            f"email_mismatches={len(data.drift['email_mismatches'])} "
            f"metadata_mismatches={len(data.drift['metadata_mismatches'])}"
        )
        drift_labels = (
            "missing",
            "unexpected",
            "email_mismatches",
            "metadata_mismatches",
        )
        for label in drift_labels:
            if data.drift[label]:
                self.stdout.write(f"{label}: {', '.join(data.drift[label])}")


def expected_members(payload):
    members = {}
    payload_members = payload["members"]
    for member in payload_members:
        if member.get("status", "active") == "removed":
            continue
        source_object_key = member["source_object_key"]
        member_record = {
            "email": member["email"].strip().lower(),
            "metadata": member.get("metadata") or {},
        }
        members[source_object_key] = member_record
    return members


def actual_members(response):
    members = {}
    response_members = response.get("members", [])
    for member in response_members:
        if member.get("status", "active") == "removed":
            continue
        source_object_key = member["source_object_key"]
        member_record = {
            "email": member["email"].strip().lower(),
            "metadata": member.get("metadata") or {},
        }
        members[source_object_key] = member_record
    return members


def option_validation_errors(options):
    kind = options["kind"]
    checks = (
        invalid_homework_filter(kind, options),
        invalid_project_filter(kind, options),
        invalid_limit(options),
    )
    return (error for error in checks if error)


def invalid_homework_filter(kind, options):
    if kind == "homework" or not options["homework_slug"]:
        return ""
    return "--homework-slug can only be used with kind=homework."


def invalid_project_filter(kind, options):
    if kind in {"project", "project-passed"} or not options["project_slug"]:
        return ""
    return (
        "--project-slug can only be used with kind=project or "
        "kind=project-passed."
    )


def invalid_limit(options):
    if 1 <= options["limit"] <= 10000:
        return ""
    return "--limit must be between 1 and 10000."


def compare_members(expected, actual):
    expected_keys = set(expected)
    actual_keys = set(actual)
    shared_keys = expected_keys & actual_keys
    drift = {
        "missing": sorted(expected_keys - actual_keys),
        "unexpected": sorted(actual_keys - expected_keys),
        "email_mismatches": member_field_mismatches(
            expected, actual, shared_keys, "email"
        ),
        "metadata_mismatches": member_field_mismatches(
            expected, actual, shared_keys, "metadata"
        ),
    }
    drift["has_drift"] = has_member_drift(drift)
    return drift


def member_field_mismatches(expected, actual, shared_keys, field):
    return sorted(
        key for key in shared_keys if expected[key][field] != actual[key][field]
    )


def has_member_drift(drift):
    return any(
        drift[label]
        for label in (
            "missing",
            "unexpected",
            "email_mismatches",
            "metadata_mismatches",
        )
    )
