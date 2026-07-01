from dataclasses import dataclass
import time

from botocore.exceptions import BotoCoreError, ClientError
from django.core.management.base import CommandError
import requests

from course_management.datamailer.client import (
    DatamailerClient,
    DatamailerConfig,
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
class ImportJobStatusData:
    list_key: str
    job_id: str
    job: dict
    write: object


def create_import_job(import_data, write):
    upload, response = safe_create_import_job_response(import_data)
    job = (response or {}).get("import_job", {})
    job_id = job.get("id")
    created_data = ImportJobCreatedData(
        list_key=import_data.list_key,
        upload=upload,
        job=job,
        job_id=job_id,
    )
    write_import_job_created(created_data, write)
    if import_data.options.wait_for_import:
        wait_data = ImportJobWaitData(
            client=import_data.client,
            list_key=import_data.list_key,
            job_id=job_id,
            timeout=import_data.options.timeout,
            poll_interval=import_data.options.poll_interval,
        )
        wait_for_created_import_job(wait_data, write)


def safe_create_import_job_response(import_data):
    try:
        return create_import_job_response(import_data)
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


def create_import_job_response(import_data):
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


def write_import_job_created(data, write):
    status = data.job.get("status", "unknown")
    write(
        "Created import job for "
        f"{data.list_key}: job_id={data.job_id}; status={status}; "
        f"rows={data.upload['row_count']}; s3_key={data.upload['s3_key']}"
    )


def wait_for_created_import_job(data, write):
    if not data.job_id:
        raise CommandError(
            "Datamailer did not return an import job id for "
            f"{data.list_key}."
        )
    wait_for_import_job(data, write)


def wait_for_import_job(data, write):
    deadline = time.monotonic() + data.timeout
    while True:
        job = import_job(data.client, data.list_key, data.job_id)
        status_data = ImportJobStatusData(
            list_key=data.list_key,
            job_id=data.job_id,
            job=job,
            write=write,
        )
        if handle_import_job_status(status_data):
            return
        if time.monotonic() >= deadline:
            raise CommandError(
                "Timed out waiting for Datamailer import job "
                f"{data.job_id} for {data.list_key}; "
                f"last status={job.get('status')}"
            )
        time.sleep(data.poll_interval)


def import_job(client, list_key, job_id):
    response = client.recipient_list_import(list_key, job_id)
    response_body = response or {}
    import_job_data = response_body.get("import_job", {})
    return import_job_data


def handle_import_job_status(data):
    status = data.job.get("status")
    if status == "succeeded":
        write_import_job_succeeded(data)
        return True
    if status == "failed":
        raise CommandError(
            "Datamailer import job failed for "
            f"{data.list_key}: job_id={data.job_id}; "
            f"error={data.job.get('error')}"
        )
    return False


def write_import_job_succeeded(data):
    data.write(
        "Import job succeeded for "
        f"{data.list_key}: job_id={data.job_id}; "
        f"rows={data.job.get('row_count')}; "
        f"created={data.job.get('created_count')}; "
        f"updated={data.job.get('updated_count')}; "
        f"removed={data.job.get('removed_count')}"
    )
