from django.core.management.base import BaseCommand, CommandError

from course_management.datamailer.client import (
    DatamailerClient,
    DatamailerConfig,
)
from course_management.datamailer.recipient_list_audit import (
    AuditRunData,
    audit_batches_against_datamailer,
)
from course_management.datamailer.recipient_list_batches import (
    build_batches,
)
from course_management.datamailer.recipient_list_sources import (
    RECIPIENT_LIST_KINDS,
)


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
        batches = build_batches(
            options["kind"],
            course_slug=options["course_slug"],
            homework_slug=options["homework_slug"],
            project_slug=options["project_slug"],
        )
        if not batches:
            self.stdout.write(
                "No Datamailer recipient-list members to audit."
            )
            return

        audit_data = recipient_list_audit_run_data(
            config,
            batches,
            options,
        )
        drift_count = audit_batches_against_datamailer(
            audit_data,
            self.stdout.write,
        )
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


def recipient_list_audit_run_data(config, batches, options):
    client = DatamailerClient(config)
    audit_data = AuditRunData(
        client=client,
        config=config,
        batches=batches,
        limit=options["limit"],
        repair=options["repair"],
    )
    return audit_data


def option_validation_errors(options):
    kind = options["kind"]
    homework_error = invalid_homework_filter(kind, options)
    project_error = invalid_project_filter(kind, options)
    limit_error = invalid_limit(options)
    checks = (
        homework_error,
        project_error,
        limit_error,
    )
    errors = []
    for error in checks:
        if error:
            errors.append(error)
    return errors


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
