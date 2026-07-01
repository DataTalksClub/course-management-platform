from dataclasses import dataclass
import time

from botocore.exceptions import BotoCoreError, ClientError
import requests
from django.core.management.base import BaseCommand, CommandError

from course_management.datamailer.client import (
    DatamailerClient,
    DatamailerConfig,
)
from course_management.datamailer.recipient_list_batches import (
    PROJECT_FILTER_KINDS,
    RECIPIENT_LIST_KINDS,
    build_batches,
)
from course_management.datamailer.recipient_list_imports import (
    import_idempotency_key,
    upload_import_file,
)


@dataclass(frozen=True)
class ImportJobOptions:
    remove_absent: bool
    wait_for_import: bool
    timeout: int
    poll_interval: float


@dataclass(frozen=True)
class ImportJobData:
    client: DatamailerClient
    config: DatamailerConfig
    kind: str
    list_key: str
    payload: dict
    options: ImportJobOptions


@dataclass(frozen=True)
class ImportJobCreatedData:
    list_key: str
    upload: dict
    job: dict
    job_id: str | None


@dataclass(frozen=True)
class ImportJobWaitData:
    client: DatamailerClient
    list_key: str
    job_id: str | None
    timeout: int
    poll_interval: float


@dataclass(frozen=True)
class InlineSyncData:
    client: DatamailerClient
    config: DatamailerConfig
    list_key: str
    payload: dict
    reconcile: bool


@dataclass(frozen=True)
class RecipientListSyncRequest:
    config: DatamailerConfig
    kind: str
    batches: dict
    options: dict


@dataclass(frozen=True)
class RecipientListSyncData:
    client: DatamailerClient
    config: DatamailerConfig
    kind: str
    batches: dict
    reconcile: bool
    import_by_reference: bool
    import_options: ImportJobOptions


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


class Command(BaseCommand):
    help = "Backfill Datamailer recipient lists from CMP registrations, enrollments, and submissions."

    def add_arguments(self, parser):
        self.add_source_arguments(parser)
        self.add_filter_arguments(parser)
        self.add_import_job_arguments(parser)
        self.add_execution_arguments(parser)

    def add_source_arguments(self, parser):
        parser.add_argument(
            "kind",
            choices=RECIPIENT_LIST_KINDS,
            help="CMP source to sync into Datamailer recipient lists.",
        )

    def add_filter_arguments(self, parser):
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

    def add_import_job_arguments(self, parser):
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

    def add_execution_arguments(self, parser):
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

    def handle(self, *args, **options):
        config = self.get_datamailer_config()
        kind = options["kind"]
        self.validate_options(kind, options)

        batches = self.get_batches(kind, options)
        if not batches:
            self.stdout.write(
                "No Datamailer recipient-list members to sync."
            )
            return

        self.write_batch_summary(batches)

        if options["dry_run"]:
            self.write_dry_run(batches, options)
            return

        sync_request = RecipientListSyncRequest(
            config=config,
            kind=kind,
            batches=batches,
            options=options,
        )
        self.sync_batches(sync_request)

    def get_datamailer_config(self):
        config = DatamailerConfig.from_settings()
        if config is None:
            raise CommandError(
                "Datamailer is not configured. Set DATAMAILER_URL, "
                "DATAMAILER_API_KEY, DATAMAILER_CLIENT, and DATAMAILER_AUDIENCE."
            )
        return config

    def validate_options(self, kind, options):
        validate_recipient_list_options(kind, options)

    def get_batches(self, kind, options):
        return build_batches(
            kind,
            course_slug=options["course_slug"],
            homework_slug=options["homework_slug"],
            project_slug=options["project_slug"],
        )

    def write_batch_summary(self, batches):
        total_members = 0
        payloads = batches.values()
        for payload in payloads:
            total_members += len(payload["members"])
        self.stdout.write(
            f"Prepared {len(batches)} recipient list(s), {total_members} member(s)."
        )

    def write_dry_run(self, batches, options):
        for list_key, payload in batches.items():
            self.stdout.write(
                f"{list_key}: {len(payload['members'])} member(s)"
            )
            if options["import_by_reference"]:
                self.stdout.write(
                    f"{list_key}: would create import job"
                )

    def sync_batches(self, request):
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
        self._sync_batches(sync_data)

    def _sync_batches(self, data):
        for list_key, payload in data.batches.items():
            if data.import_by_reference:
                import_data = self._import_job_data(
                    data,
                    list_key,
                    payload,
                )
                self._create_import_job(import_data)
                continue

            inline_data = InlineSyncData(
                client=data.client,
                config=data.config,
                list_key=list_key,
                payload=payload,
                reconcile=data.reconcile,
            )
            response = self._sync_inline_batch(inline_data)
            self._write_sync_result(list_key, payload, response)

    def _import_job_data(self, data, list_key, payload):
        return ImportJobData(
            client=data.client,
            config=data.config,
            kind=data.kind,
            list_key=list_key,
            payload=payload,
            options=data.import_options,
        )

    def _sync_inline_batch(self, data):
        try:
            if data.reconcile:
                return data.client.reconcile_recipient_list_members(
                    data.list_key, data.payload
                )
            return data.client.bulk_upsert_recipient_list_members(
                data.list_key, data.payload
            )
        except requests.RequestException as exc:
            if data.config.strict:
                raise
            raise CommandError(
                f"Datamailer sync failed for {data.list_key}: {exc}"
            ) from exc

    def _write_sync_result(self, list_key, payload, response):
        active_count = self._active_member_count(response)
        suffix = (
            f"; active={active_count}"
            if active_count is not None
            else ""
        )
        self.stdout.write(
            f"Synced {list_key}: {len(payload['members'])} member(s){suffix}"
        )

    def _active_member_count(self, response):
        if not response:
            return None
        return response.get("recipient_list", {}).get(
            "active_member_count"
        )

    def _create_import_job(self, import_data):
        upload, response = self._safe_create_import_job_response(
            import_data
        )
        job = (response or {}).get("import_job", {})
        job_id = job.get("id")
        created_data = ImportJobCreatedData(
            list_key=import_data.list_key,
            upload=upload,
            job=job,
            job_id=job_id,
        )
        self._write_import_job_created(created_data)
        if import_data.options.wait_for_import:
            wait_data = ImportJobWaitData(
                client=import_data.client,
                list_key=import_data.list_key,
                job_id=job_id,
                timeout=import_data.options.timeout,
                poll_interval=import_data.options.poll_interval,
            )
            self._wait_for_created_import_job(wait_data)

    def _safe_create_import_job_response(self, import_data):
        try:
            return self._create_import_job_response(import_data)
        except (
            BotoCoreError,
            ClientError,
            requests.RequestException,
        ) as exc:
            if import_data.config.strict:
                raise
            raise CommandError(
                "Datamailer import job creation failed for "
                f"{import_data.list_key}: {exc}"
            ) from exc

    def _create_import_job_response(self, import_data):
        upload = upload_import_file(
            import_data.kind,
            import_data.config,
            import_data.list_key,
            import_data.payload,
        )
        idempotency_key = import_idempotency_key(
            import_data.kind,
            import_data.list_key,
            upload["content_sha256"],
            remove_absent=import_data.options.remove_absent,
        )
        import_payload = {
            "source_url": upload["source_url"],
            "idempotency_key": idempotency_key,
            "list": import_data.payload["list"],
            "remove_absent": import_data.options.remove_absent,
        }
        response = import_data.client.create_recipient_list_import(
            import_data.list_key,
            import_payload,
        )
        return upload, response

    def _write_import_job_created(self, data):
        status = data.job.get("status", "unknown")
        self.stdout.write(
            "Created import job for "
            f"{data.list_key}: job_id={data.job_id}; status={status}; "
            f"rows={data.upload['row_count']}; s3_key={data.upload['s3_key']}"
        )

    def _wait_for_created_import_job(self, data):
        if not data.job_id:
            raise CommandError(
                "Datamailer did not return an import job id for "
                f"{data.list_key}."
            )
        self._wait_for_import_job(data)

    def _wait_for_import_job(self, data):
        deadline = time.monotonic() + data.timeout
        while True:
            job = self._import_job(data.client, data.list_key, data.job_id)
            if self._handle_import_job_status(
                data.list_key,
                data.job_id,
                job,
            ):
                return
            if time.monotonic() >= deadline:
                raise CommandError(
                    "Timed out waiting for Datamailer import job "
                    f"{data.job_id} for {data.list_key}; "
                    f"last status={job.get('status')}"
                )
            time.sleep(data.poll_interval)

    def _import_job(self, client, list_key, job_id):
        response = client.recipient_list_import(list_key, job_id)
        response_body = response or {}
        import_job = response_body.get("import_job", {})
        return import_job

    def _handle_import_job_status(self, list_key, job_id, job):
        status = job.get("status")
        if status == "succeeded":
            self._write_import_job_succeeded(list_key, job_id, job)
            return True
        if status == "failed":
            raise CommandError(
                "Datamailer import job failed for "
                f"{list_key}: job_id={job_id}; error={job.get('error')}"
            )
        return False

    def _write_import_job_succeeded(self, list_key, job_id, job):
        self.stdout.write(
            "Import job succeeded for "
            f"{list_key}: job_id={job_id}; "
            f"rows={job.get('row_count')}; "
            f"created={job.get('created_count')}; "
            f"updated={job.get('updated_count')}; "
            f"removed={job.get('removed_count')}"
        )
