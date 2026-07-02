from dataclasses import dataclass

from django.core.management.base import BaseCommand, CommandError

from course_management.datamailer.client import (
    DatamailerClient,
    DatamailerConfig,
)
from course_management.datamailer.recipient_list_batches import (
    build_batches as build_recipient_list_batches,
)
from course_management.datamailer.recipient_list_sources import (
    PROJECT_FILTER_KINDS,
    RECIPIENT_LIST_KINDS,
)
from course_management.datamailer.recipient_list_import_jobs import (
    ImportJobOptions,
)
from course_management.datamailer.recipient_list_sync import (
    RecipientListSyncData,
    sync_recipient_list_batches,
)


@dataclass(frozen=True)
class RecipientListSyncRequest:
    config: DatamailerConfig
    kind: str
    batches: dict
    options: dict


def validate_recipient_list_options(kind, options):
    _validate_homework_filter(kind, options)
    _validate_project_filter(kind, options)
    _validate_import_wait_options(options)
    _validate_positive_import_option(
        options,
        "import_timeout",
        "--import-timeout",
    )
    _validate_positive_import_option(
        options,
        "import_poll_interval",
        "--import-poll-interval",
    )


def _validate_homework_filter(kind, options):
    if kind == "homework" or not options["homework_slug"]:
        return

    raise CommandError(
        "--homework-slug can only be used with kind=homework."
    )


def _validate_project_filter(kind, options):
    if kind in PROJECT_FILTER_KINDS or not options["project_slug"]:
        return

    raise CommandError(
        "--project-slug can only be used with kind=project or kind=project-passed."
    )


def _validate_import_wait_options(options):
    if not options["wait_for_import"] or options["import_by_reference"]:
        return

    raise CommandError(
        "--wait-for-import requires --import-by-reference."
    )


def _validate_positive_import_option(options, option_key, option_name):
    if options[option_key] > 0:
        return

    raise CommandError(f"{option_name} must be positive.")


def add_source_arguments(parser):
    parser.add_argument(
        "kind",
        choices=RECIPIENT_LIST_KINDS,
        help="CMP source to sync into Datamailer recipient lists.",
    )


def add_filter_arguments(parser):
    parser.add_argument(
        "--course-slug",
        default="",
        help="Limit the sync to one course cohort slug.",
    )
    parser.add_argument(
        "--homework-slug",
        default="",
        help="Limit homework sync to one homework slug.",
    )
    parser.add_argument(
        "--project-slug",
        default="",
        help="Limit project sync to one project slug.",
    )


def add_import_job_arguments(parser):
    parser.add_argument(
        "--import-by-reference",
        action="store_true",
        help=(
            "Upload JSONL to CMP S3 and create Datamailer async import "
            "jobs instead of sending members inline."
        ),
    )
    parser.add_argument(
        "--wait-for-import",
        action="store_true",
        help="Poll Datamailer import jobs until they succeed or fail.",
    )
    parser.add_argument(
        "--import-timeout",
        type=int,
        default=600,
        help="Seconds to wait for each import job with --wait-for-import.",
    )
    parser.add_argument(
        "--import-poll-interval",
        type=float,
        default=5.0,
        help="Seconds between import job status checks.",
    )


def add_execution_arguments(parser):
    parser.add_argument(
        "--reconcile",
        action="store_true",
        help="Mark existing Datamailer members absent from CMP as removed.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned batches without calling Datamailer.",
    )


def recipient_list_batches(kind, options):
    batches = build_recipient_list_batches(
        kind,
        course_slug=options["course_slug"],
        homework_slug=options["homework_slug"],
        project_slug=options["project_slug"],
    )
    return batches


def write_batch_summary(write_line, batches):
    total_members = 0
    for payload in batches.values():
        total_members += len(payload["members"])
    write_line(
        f"Prepared {len(batches)} recipient list(s), {total_members} member(s)."
    )


def write_dry_run(write_line, batches, options):
    for list_key, payload in batches.items():
        write_line(f"{list_key}: {len(payload['members'])} member(s)")
        if options["import_by_reference"]:
            write_line(f"{list_key}: would create import job")


def sync_batches(request, write_line):
    client = DatamailerClient(request.config)
    import_options = ImportJobOptions(
        remove_absent=request.options["reconcile"],
        wait_for_import=request.options["wait_for_import"],
        timeout=request.options["import_timeout"],
        poll_interval=request.options["import_poll_interval"],
    )
    sync_data = RecipientListSyncData(
        client=client,
        config=request.config,
        kind=request.kind,
        batches=request.batches,
        reconcile=request.options["reconcile"],
        import_by_reference=request.options["import_by_reference"],
        import_options=import_options,
    )
    sync_recipient_list_batches(sync_data, write_line)


class Command(BaseCommand):
    help = "Backfill Datamailer recipient lists from CMP registrations, enrollments, and submissions."

    def add_arguments(self, parser):
        add_source_arguments(parser)
        add_filter_arguments(parser)
        add_import_job_arguments(parser)
        add_execution_arguments(parser)

    def handle(self, *args, **options):
        config = self.get_datamailer_config()
        kind = options["kind"]
        validate_recipient_list_options(kind, options)

        batches = recipient_list_batches(kind, options)
        if not batches:
            self.stdout.write(
                "No Datamailer recipient-list members to sync."
            )
            return

        write_batch_summary(self.stdout.write, batches)

        if options["dry_run"]:
            write_dry_run(self.stdout.write, batches, options)
            return

        sync_request = RecipientListSyncRequest(
            config=config,
            kind=kind,
            batches=batches,
            options=options,
        )
        sync_batches(sync_request, self.stdout.write)

    def get_datamailer_config(self):
        config = DatamailerConfig.from_settings()
        if config is None:
            raise CommandError(
                "Datamailer is not configured. Set DATAMAILER_URL, "
                "DATAMAILER_API_KEY, DATAMAILER_CLIENT, and DATAMAILER_AUDIENCE."
        )
        return config
