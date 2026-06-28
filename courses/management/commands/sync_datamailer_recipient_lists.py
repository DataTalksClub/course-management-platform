from collections import OrderedDict
import hashlib
import json
import re
import time

import boto3
from botocore.exceptions import BotoCoreError, ClientError
import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from course_management.datamailer import (
    DatamailerClient,
    DatamailerConfig,
    course_graduate_recipient_list_payload,
    enrollment_recipient_list_payload,
    homework_submission_recipient_list_payload,
    project_passed_recipient_list_payload,
    project_submission_recipient_list_payload,
    registration_recipient_list_payload,
)
from courses.models import (
    CourseRegistration,
    Enrollment,
    Project,
    ProjectSubmission,
    Submission,
)


RECIPIENT_LIST_KINDS = [
    "registrations",
    "enrollments",
    "homework",
    "project",
    "project-passed",
    "graduates",
]


def add_member_to_batches(
    batches, list_key, source_object_key, payload
):
    batch = batches.setdefault(
        list_key,
        {
            "audience": payload["audience"],
            "client": payload["client"],
            "list": payload["list"],
            "members": [],
        },
    )
    batch["members"].append(
        {
            "source_object_key": source_object_key,
            "email": payload["member"]["email"],
            "status": payload["member"]["status"],
            "metadata": payload["member"]["metadata"],
        }
    )


def add_payload_members_to_batches(batches, list_key, payload):
    batch = batches.setdefault(
        list_key,
        {
            "audience": payload["audience"],
            "client": payload["client"],
            "list": payload["list"],
            "members": [],
        },
    )
    batch["members"].extend(payload["members"])


def registration_queryset(course_slug):
    queryset = CourseRegistration.objects.select_related(
        "campaign", "course", "user"
    ).order_by("pk")
    if course_slug:
        queryset = queryset.filter(course__slug=course_slug)
    return queryset


def enrollment_queryset(course_slug):
    queryset = Enrollment.objects.select_related(
        "student",
        "course",
    ).order_by("pk")
    if course_slug:
        queryset = queryset.filter(course__slug=course_slug)
    return queryset


def homework_submission_queryset(course_slug, homework_slug):
    queryset = Submission.objects.select_related(
        "student",
        "homework",
        "homework__course",
    ).order_by("pk")
    if course_slug:
        queryset = queryset.filter(homework__course__slug=course_slug)
    if homework_slug:
        queryset = queryset.filter(homework__slug=homework_slug)
    return queryset


def project_submission_queryset(course_slug, project_slug):
    queryset = ProjectSubmission.objects.select_related(
        "student",
        "project",
        "project__course",
    ).order_by("pk")
    if course_slug:
        queryset = queryset.filter(project__course__slug=course_slug)
    if project_slug:
        queryset = queryset.filter(project__slug=project_slug)
    return queryset


def project_queryset(course_slug, project_slug):
    queryset = ProjectSubmission.objects.select_related(
        "project",
        "project__course",
    ).filter(passed=True)
    if course_slug:
        queryset = queryset.filter(project__course__slug=course_slug)
    if project_slug:
        queryset = queryset.filter(project__slug=project_slug)
    project_ids = (
        queryset.order_by("project_id")
        .values_list("project_id", flat=True)
        .distinct()
    )
    return (
        Project.objects.filter(pk__in=project_ids)
        .select_related("course")
        .order_by("pk")
    )


def graduates_queryset(course_slug):
    queryset = (
        Enrollment.objects.select_related("student", "course")
        .exclude(certificate_url__isnull=True)
        .exclude(certificate_url="")
        .order_by("pk")
    )
    if course_slug:
        queryset = queryset.filter(course__slug=course_slug)
    return queryset


# kind -> (queryset(course_slug, homework_slug, project_slug), payload_builder)
_RECIPIENT_LIST_SOURCES = {
    "registrations": (
        lambda c, h, p: registration_queryset(c),
        registration_recipient_list_payload,
    ),
    "enrollments": (
        lambda c, h, p: enrollment_queryset(c),
        enrollment_recipient_list_payload,
    ),
    "homework": (
        lambda c, h, p: homework_submission_queryset(c, h),
        homework_submission_recipient_list_payload,
    ),
    "project": (
        lambda c, h, p: project_submission_queryset(c, p),
        project_submission_recipient_list_payload,
    ),
    "project-passed": (
        lambda c, h, p: project_queryset(c, p),
        project_passed_recipient_list_payload,
    ),
    "graduates": (
        lambda c, h, p: graduates_queryset(c),
        course_graduate_recipient_list_payload,
    ),
}


def build_batches(
    kind, *, course_slug="", homework_slug="", project_slug=""
):
    source = _RECIPIENT_LIST_SOURCES.get(kind)
    if source is None:
        raise CommandError(f"Unknown recipient list kind: {kind}")

    queryset_fn, payload_for = source
    batches = OrderedDict()
    for obj in queryset_fn(course_slug, homework_slug, project_slug):
        item = payload_for(obj)
        if item is None:
            continue
        if len(item) == 2:
            list_key, payload = item
            add_payload_members_to_batches(batches, list_key, payload)
        else:
            list_key, source_object_key, payload = item
            add_member_to_batches(
                batches, list_key, source_object_key, payload
            )
    return batches


def import_member_jsonl(members):
    lines = [
        json.dumps(member, sort_keys=True, separators=(",", ":"))
        for member in members
    ]
    return ("\n".join(lines) + "\n").encode("utf-8")


def safe_s3_key_part(value):
    safe = re.sub(r"[^A-Za-z0-9._:@=-]+", "_", value.strip())
    return safe.strip("._") or "recipient-list"


def import_object_key(kind, config, list_key, content_sha256):
    parts = [
        getattr(settings, "DATAMAILER_IMPORT_S3_PREFIX", ""),
        config.client,
        config.audience,
        kind,
        safe_s3_key_part(list_key),
        f"{content_sha256}.jsonl",
    ]
    return "/".join(part.strip("/") for part in parts if part)


def upload_import_file(kind, config, list_key, payload):
    bucket = getattr(settings, "DATAMAILER_IMPORT_S3_BUCKET", "")
    if not bucket:
        raise CommandError(
            "DATAMAILER_IMPORT_S3_BUCKET must be set when using "
            "--import-by-reference."
        )

    body = import_member_jsonl(payload["members"])
    content_sha256 = hashlib.sha256(body).hexdigest()
    key = import_object_key(kind, config, list_key, content_sha256)
    region = getattr(settings, "DATAMAILER_IMPORT_S3_REGION", "")
    s3_kwargs = {"region_name": region} if region else {}
    s3 = boto3.client("s3", **s3_kwargs)
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType="application/x-ndjson",
        Metadata={
            "client": config.client,
            "audience": config.audience,
            "list-key-sha256": hashlib.sha256(
                list_key.encode("utf-8")
            ).hexdigest(),
            "content-sha256": content_sha256,
        },
    )
    source_url = s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=getattr(
            settings, "DATAMAILER_IMPORT_URL_EXPIRES_SECONDS", 3600
        ),
        HttpMethod="GET",
    )
    return {
        "source_url": source_url,
        "s3_bucket": bucket,
        "s3_key": key,
        "content_sha256": content_sha256,
        "row_count": len(payload["members"]),
    }


def import_idempotency_key(
    kind, list_key, content_sha256, *, remove_absent
):
    remove_absent_value = "true" if remove_absent else "false"
    list_key_sha256 = hashlib.sha256(
        list_key.encode("utf-8")
    ).hexdigest()
    return (
        "cmp-recipient-list-import:"
        f"{kind}:{list_key_sha256}:{content_sha256}:"
        f"remove-absent-{remove_absent_value}"
    )


class Command(BaseCommand):
    help = "Backfill Datamailer recipient lists from CMP registrations, enrollments, and submissions."

    def add_arguments(self, parser):
        self.add_source_arguments(parser)
        self.add_filter_arguments(parser)
        self.add_import_arguments(parser)
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

    def add_import_arguments(self, parser):
        parser.add_argument(
            "--reconcile",
            action="store_true",
            help="Mark existing Datamailer members absent from CMP as removed.",
        )
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

        self.sync_batches(config, kind, batches, options)

    def get_datamailer_config(self):
        config = DatamailerConfig.from_settings()
        if config is None:
            raise CommandError(
                "Datamailer is not configured. Set DATAMAILER_URL, "
                "DATAMAILER_API_KEY, DATAMAILER_CLIENT, and DATAMAILER_AUDIENCE."
            )
        return config

    def validate_options(self, kind, options):
        if kind != "homework" and options["homework_slug"]:
            raise CommandError(
                "--homework-slug can only be used with kind=homework."
            )
        if (
            kind not in {"project", "project-passed"}
            and options["project_slug"]
        ):
            raise CommandError(
                "--project-slug can only be used with kind=project or kind=project-passed."
            )
        if (
            options["wait_for_import"]
            and not options["import_by_reference"]
        ):
            raise CommandError(
                "--wait-for-import requires --import-by-reference."
            )
        if options["import_timeout"] <= 0:
            raise CommandError("--import-timeout must be positive.")
        if options["import_poll_interval"] <= 0:
            raise CommandError(
                "--import-poll-interval must be positive."
            )

    def get_batches(self, kind, options):
        return build_batches(
            kind,
            course_slug=options["course_slug"],
            homework_slug=options["homework_slug"],
            project_slug=options["project_slug"],
        )

    def write_batch_summary(self, batches):
        total_members = sum(
            len(payload["members"]) for payload in batches.values()
        )
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

    def sync_batches(self, config, kind, batches, options):
        client = DatamailerClient(config)
        self._sync_batches(
            client,
            batches,
            config,
            kind=kind,
            reconcile=options["reconcile"],
            import_by_reference=options["import_by_reference"],
            wait_for_import=options["wait_for_import"],
            import_timeout=options["import_timeout"],
            import_poll_interval=options["import_poll_interval"],
        )

    def _sync_batches(
        self,
        client,
        batches,
        config,
        *,
        kind,
        reconcile,
        import_by_reference,
        wait_for_import,
        import_timeout,
        import_poll_interval,
    ):
        for list_key, payload in batches.items():
            if import_by_reference:
                self._create_import_job(
                    client,
                    config,
                    kind,
                    list_key,
                    payload,
                    remove_absent=reconcile,
                    wait_for_import=wait_for_import,
                    import_timeout=import_timeout,
                    import_poll_interval=import_poll_interval,
                )
                continue

            response = self._sync_inline_batch(
                client, config, list_key, payload, reconcile=reconcile
            )
            self._write_sync_result(list_key, payload, response)

    def _sync_inline_batch(
        self, client, config, list_key, payload, *, reconcile
    ):
        try:
            if reconcile:
                return client.reconcile_recipient_list_members(
                    list_key, payload
                )
            return client.bulk_upsert_recipient_list_members(
                list_key, payload
            )
        except requests.RequestException as exc:
            if config.strict:
                raise
            raise CommandError(
                f"Datamailer sync failed for {list_key}: {exc}"
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

    def _create_import_job(
        self,
        client,
        config,
        kind,
        list_key,
        payload,
        *,
        remove_absent,
        wait_for_import,
        import_timeout,
        import_poll_interval,
    ):
        try:
            upload, response = self._create_import_job_response(
                client,
                config,
                kind,
                list_key,
                payload,
                remove_absent=remove_absent,
            )
        except (
            BotoCoreError,
            ClientError,
            requests.RequestException,
        ) as exc:
            if config.strict:
                raise
            raise CommandError(
                f"Datamailer import job creation failed for {list_key}: {exc}"
            ) from exc

        job = (response or {}).get("import_job", {})
        job_id = job.get("id")
        self._write_import_job_created(list_key, upload, job, job_id)
        if wait_for_import:
            self._wait_for_created_import_job(
                client,
                list_key,
                job_id,
                timeout=import_timeout,
                poll_interval=import_poll_interval,
            )

    def _create_import_job_response(
        self, client, config, kind, list_key, payload, *, remove_absent
    ):
        upload = upload_import_file(kind, config, list_key, payload)
        response = client.create_recipient_list_import(
            list_key,
            {
                "source_url": upload["source_url"],
                "idempotency_key": import_idempotency_key(
                    kind,
                    list_key,
                    upload["content_sha256"],
                    remove_absent=remove_absent,
                ),
                "list": payload["list"],
                "remove_absent": remove_absent,
            },
        )
        return upload, response

    def _write_import_job_created(self, list_key, upload, job, job_id):
        status = job.get("status", "unknown")
        self.stdout.write(
            "Created import job for "
            f"{list_key}: job_id={job_id}; status={status}; "
            f"rows={upload['row_count']}; s3_key={upload['s3_key']}"
        )

    def _wait_for_created_import_job(
        self, client, list_key, job_id, *, timeout, poll_interval
    ):
        if not job_id:
            raise CommandError(
                f"Datamailer did not return an import job id for {list_key}."
            )
        self._wait_for_import_job(
            client,
            list_key,
            job_id,
            timeout=timeout,
            poll_interval=poll_interval,
        )

    def _wait_for_import_job(
        self,
        client,
        list_key,
        job_id,
        *,
        timeout,
        poll_interval,
    ):
        deadline = time.monotonic() + timeout
        while True:
            response = client.recipient_list_import(list_key, job_id)
            job = (response or {}).get("import_job", {})
            status = job.get("status")
            if status == "succeeded":
                self.stdout.write(
                    "Import job succeeded for "
                    f"{list_key}: job_id={job_id}; "
                    f"rows={job.get('row_count')}; "
                    f"created={job.get('created_count')}; "
                    f"updated={job.get('updated_count')}; "
                    f"removed={job.get('removed_count')}"
                )
                return
            if status == "failed":
                raise CommandError(
                    "Datamailer import job failed for "
                    f"{list_key}: job_id={job_id}; error={job.get('error')}"
                )
            if time.monotonic() >= deadline:
                raise CommandError(
                    "Timed out waiting for Datamailer import job "
                    f"{job_id} for {list_key}; last status={status}"
                )
            time.sleep(poll_interval)
