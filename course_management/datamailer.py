import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import requests
from django.conf import settings
from django.urls import reverse

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DatamailerConfig:
    url: str
    api_key: str
    client: str
    audience: str
    from_email: str = ""
    strict: bool = False

    @classmethod
    def from_settings(cls) -> "DatamailerConfig | None":
        url = getattr(settings, "DATAMAILER_URL", "")
        api_key = getattr(settings, "DATAMAILER_API_KEY", "")
        client = getattr(settings, "DATAMAILER_CLIENT", "")
        audience = getattr(settings, "DATAMAILER_AUDIENCE", "")
        from_email = getattr(settings, "DATAMAILER_FROM_EMAIL", "")

        if not all([url, api_key, client, audience]):
            return None

        strict = getattr(settings, "DATAMAILER_STRICT", False)
        return cls(
            url=url.rstrip("/"),
            api_key=api_key,
            client=client,
            audience=audience,
            from_email=from_email,
            strict=strict,
        )


class DatamailerClient:
    def __init__(
        self,
        config: DatamailerConfig,
        session: requests.Session | None = None,
    ):
        self.config = config
        self.session = session or requests.Session()

    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        url = f"{self.config.url}{path}"
        request_kwargs: dict[str, Any] = {
            "json": json,
            "timeout": 10,
            "headers": {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
        }
        if params is not None:
            request_kwargs["params"] = params

        response = self.session.request(
            method,
            url,
            **request_kwargs,
        )
        response.raise_for_status()

        if not response.content:
            return None

        return response.json()

    def upsert_contact(
        self, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        return self.request("POST", "/api/contacts", json=payload)

    def send_transactional(
        self, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        return self.request(
            "POST",
            "/api/transactional/send",
            json=payload,
        )

    def contact_status(self, email: str) -> dict[str, Any] | None:
        return self.request(
            "GET",
            "/api/contacts/status",
            params={
                "email": email,
                "audience": self.config.audience,
                "client": self.config.client,
            },
        )

    def contact_history(
        self,
        contact_id: int,
        *,
        limit: int = 25,
    ) -> dict[str, Any] | None:
        return self.request(
            "GET",
            f"/api/contacts/{contact_id}/history",
            params={
                "audience": self.config.audience,
                "client": self.config.client,
                "limit": limit,
            },
        )

    def transactional_message_status(
        self,
        message_id: int,
    ) -> dict[str, Any] | None:
        return self.request(
            "GET",
            f"/api/transactional/messages/{message_id}",
        )

    def upsert_recipient_list_member(
        self,
        list_key: str,
        source_object_key: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        return self.request(
            "PUT",
            f"/api/recipient-lists/{list_key}/members/{source_object_key}",
            json=payload,
        )

    def bulk_upsert_recipient_list_members(
        self,
        list_key: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        return self.request(
            "POST",
            f"/api/recipient-lists/{list_key}/members/bulk-upsert",
            json=payload,
        )

    def reconcile_recipient_list_members(
        self,
        list_key: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        return self.request(
            "POST",
            f"/api/recipient-lists/{list_key}/members/reconcile",
            json=payload,
        )

    def send_recipient_list_transactional(
        self,
        list_key: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        return self.request(
            "POST",
            f"/api/recipient-lists/{list_key}/transactional-send",
            json=payload,
        )


def get_datamailer_client() -> DatamailerClient | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None
    return DatamailerClient(config)


def datamailer_enabled() -> bool:
    return DatamailerConfig.from_settings() is not None


def course_family_slug(course) -> str:
    slug = course.slug
    return re.sub(r"[-_ ]?\d{4}$", "", slug).strip("-_ ") or slug


def contact_tags_for_course(course) -> list[str]:
    family_slug = course_family_slug(course)
    return [
        f"course-{family_slug}",
        f"course-cohort-{course.slug}",
    ]


def contact_payload_for_user(
    user, course=None
) -> dict[str, Any] | None:
    email = (user.email or "").strip().lower()
    if not email:
        return None

    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    tags = []
    custom_fields = {
        "course_platform_user_id": str(user.pk),
        "username": user.username or "",
    }

    if course is not None:
        tags.extend(contact_tags_for_course(course))
        custom_fields["course_slug"] = course.slug
        custom_fields["course_family_slug"] = course_family_slug(course)
        custom_fields["course_cohort_slug"] = course.slug
        custom_fields["course_title"] = course.title

    return {
        "email": email,
        "audience": config.audience,
        "client": config.client,
        "status": "subscribed",
        "verified": True,
        "email_validation": {
            "status": "externally_validated",
        },
        "tags": tags,
        "custom_fields": custom_fields,
    }


def registration_list_key(registration) -> str:
    if registration.course_id:
        return f"registrants:{registration.course.slug}"
    return f"registrants:{registration.campaign.slug}"


def homework_submitters_list_key(homework) -> str:
    return f"homework-submitters:{homework.course.slug}:{homework.slug}"


def project_submitters_list_key(project) -> str:
    return f"project-submitters:{project.course.slug}:{project.slug}"


def public_url(path: str) -> str:
    base_url = getattr(settings, "PUBLIC_BASE_URL", "")
    if not base_url:
        return path
    return urljoin(f"{base_url.rstrip('/')}/", path.lstrip("/"))


def registration_contact_payload(registration) -> dict[str, Any] | None:
    email = (
        (registration.email_normalized or registration.email or "")
        .strip()
        .lower()
    )
    if not email:
        return None

    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    tags = []
    course = registration.course
    if course is not None:
        tags = contact_tags_for_course(course)

    return {
        "email": email,
        "audience": config.audience,
        "client": config.client,
        "status": "subscribed",
        "verified": True,
        "email_validation": {
            "status": "externally_validated",
        },
        "tags": tags,
    }


def recipient_list_member_payload(
    *,
    list_type: str,
    list_name: str,
    email: str,
    source_object_key: str,
    metadata: dict[str, Any],
) -> dict[str, Any] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    return {
        "audience": config.audience,
        "client": config.client,
        "list": {
            "type": list_type,
            "name": list_name,
            "metadata": metadata,
        },
        "member": {
            "email": email.strip().lower(),
            "status": "active",
            "metadata": metadata
            | {"source_object_key": source_object_key},
        },
    }


def registration_recipient_list_payload(
    registration,
) -> tuple[str, str, dict[str, Any]] | None:
    email = (
        (registration.email_normalized or registration.email or "")
        .strip()
        .lower()
    )
    if not email:
        return None

    course = registration.course
    list_key = registration_list_key(registration)
    list_name = (
        f"{course.title} registrants"
        if course is not None
        else f"{registration.campaign.title} registrants"
    )
    source_object_key = f"registration:{registration.pk}"
    metadata = {
        "registration_id": registration.pk,
        "campaign_slug": registration.campaign.slug,
        "course_slug": course.slug if course is not None else "",
        "user_id": registration.user_id,
        "registered_at": registration.created_at.isoformat()
        if registration.created_at
        else "",
        "country": registration.country,
        "region": registration.region,
        "role": registration.role,
    }
    payload = recipient_list_member_payload(
        list_type="registrants",
        list_name=list_name,
        email=email,
        source_object_key=source_object_key,
        metadata=metadata,
    )
    if payload is None:
        return None
    return list_key, source_object_key, payload


def homework_submission_recipient_list_payload(
    submission,
) -> tuple[str, str, dict[str, Any]] | None:
    email = (submission.student.email or "").strip().lower()
    if not email:
        return None

    homework = submission.homework
    course = homework.course
    list_key = homework_submitters_list_key(homework)
    source_object_key = f"homework-submission:{submission.pk}"
    metadata = {
        "submission_id": submission.pk,
        "user_id": submission.student_id,
        "course_slug": course.slug,
        "homework_slug": homework.slug,
        "submitted_at": submission.submitted_at.isoformat()
        if submission.submitted_at
        else "",
    }
    payload = recipient_list_member_payload(
        list_type="homework_submitters",
        list_name=f"{course.title} {homework.title} submitters",
        email=email,
        source_object_key=source_object_key,
        metadata=metadata,
    )
    if payload is None:
        return None
    return list_key, source_object_key, payload


def project_submission_recipient_list_payload(
    submission,
) -> tuple[str, str, dict[str, Any]] | None:
    email = (submission.student.email or "").strip().lower()
    if not email:
        return None

    project = submission.project
    course = project.course
    list_key = project_submitters_list_key(project)
    source_object_key = f"project-submission:{submission.pk}"
    metadata = {
        "submission_id": submission.pk,
        "user_id": submission.student_id,
        "course_slug": course.slug,
        "project_slug": project.slug,
        "submitted_at": submission.submitted_at.isoformat()
        if submission.submitted_at
        else "",
    }
    payload = recipient_list_member_payload(
        list_type="project_submitters",
        list_name=f"{course.title} {project.title} submitters",
        email=email,
        source_object_key=source_object_key,
        metadata=metadata,
    )
    if payload is None:
        return None
    return list_key, source_object_key, payload


def sync_contact(user, course=None) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    payload = contact_payload_for_user(user, course=course)
    if payload is None:
        return

    client = DatamailerClient(config)
    if config.from_email and "from_email" not in payload:
        payload = payload | {"from_email": config.from_email}

    try:
        client.upsert_contact(payload)
    except requests.RequestException:
        logger.exception(
            "Datamailer contact sync failed for user_id=%s",
            user.pk,
        )
        if config.strict:
            raise


def sync_registration_to_datamailer(registration) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    contact_payload = registration_contact_payload(registration)
    list_payload = registration_recipient_list_payload(registration)
    if contact_payload is None or list_payload is None:
        return

    client = DatamailerClient(config)
    try:
        client.upsert_contact(contact_payload)
        list_key, source_object_key, payload = list_payload
        client.upsert_recipient_list_member(
            list_key, source_object_key, payload
        )
    except requests.RequestException:
        logger.exception(
            "Datamailer registration sync failed for registration_id=%s",
            registration.pk,
        )
        if config.strict:
            raise


def sync_homework_submission_to_datamailer(submission) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    contact_payload = contact_payload_for_user(
        submission.student,
        course=submission.homework.course,
    )
    list_payload = homework_submission_recipient_list_payload(
        submission
    )
    if contact_payload is None or list_payload is None:
        return

    client = DatamailerClient(config)
    try:
        client.upsert_contact(contact_payload)
        list_key, source_object_key, payload = list_payload
        client.upsert_recipient_list_member(
            list_key, source_object_key, payload
        )
    except requests.RequestException:
        logger.exception(
            "Datamailer homework submission sync failed for submission_id=%s",
            submission.pk,
        )
        if config.strict:
            raise


def sync_project_submission_to_datamailer(submission) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    contact_payload = contact_payload_for_user(
        submission.student,
        course=submission.project.course,
    )
    list_payload = project_submission_recipient_list_payload(submission)
    if contact_payload is None or list_payload is None:
        return

    client = DatamailerClient(config)
    try:
        client.upsert_contact(contact_payload)
        list_key, source_object_key, payload = list_payload
        client.upsert_recipient_list_member(
            list_key, source_object_key, payload
        )
    except requests.RequestException:
        logger.exception(
            "Datamailer project submission sync failed for submission_id=%s",
            submission.pk,
        )
        if config.strict:
            raise


def homework_score_notification_payload(
    homework,
) -> tuple[str, dict[str, Any]] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    from course_management import email_templates

    course = homework.course
    list_key = homework_submitters_list_key(homework)
    course_url = public_url(
        reverse("course", kwargs={"course_slug": course.slug})
    )

    payload = {
        "audience": config.audience,
        "client": config.client,
        "template_key": email_templates.HOMEWORK_SCORE_NOTIFICATION,
        "idempotency_key": f"homework-score:{course.slug}:{homework.slug}",
        "context": {
            "course_slug": course.slug,
            "course_title": course.title,
            "homework_slug": homework.slug,
            "homework_title": homework.title,
            "course_url": course_url,
            "scores_url": course_url,
        },
        "metadata": {
            "source": "course-management-platform",
            "event": "homework_score_publication",
            "course_slug": course.slug,
            "homework_slug": homework.slug,
            "homework_id": homework.pk,
        },
    }
    if config.from_email:
        payload["from_email"] = config.from_email
    return list_key, payload


def send_homework_score_notification(homework) -> dict[str, Any] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    list_payload = homework_score_notification_payload(homework)
    if list_payload is None:
        return None

    client = DatamailerClient(config)
    try:
        list_key, payload = list_payload
        return client.send_recipient_list_transactional(
            list_key, payload
        )
    except requests.RequestException:
        logger.exception(
            "Datamailer homework score notification failed for homework_id=%s",
            homework.pk,
        )
        if config.strict:
            raise
        return None


def send_transactional_email(
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    client = DatamailerClient(config)
    if config.from_email and "from_email" not in payload:
        payload = payload | {"from_email": config.from_email}

    try:
        return client.send_transactional(payload)
    except requests.RequestException:
        logger.exception("Datamailer transactional email failed")
        if config.strict:
            raise
        return None


def get_contact_status(email: str) -> dict[str, Any] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    client = DatamailerClient(config)

    try:
        return client.contact_status(email)
    except requests.RequestException:
        logger.exception("Datamailer contact status lookup failed")
        if config.strict:
            raise
        return None


def get_contact_history(
    contact_id: int,
    *,
    limit: int = 25,
) -> dict[str, Any] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    client = DatamailerClient(config)

    try:
        return client.contact_history(contact_id, limit=limit)
    except requests.RequestException:
        logger.exception("Datamailer contact history lookup failed")
        if config.strict:
            raise
        return None


def get_email_status(
    email: str, *, limit: int = 25
) -> dict[str, Any] | None:
    status = get_contact_status(email)
    if status is None:
        return None

    contact_id = status.get("contact_id")
    history = None
    if contact_id:
        history = get_contact_history(int(contact_id), limit=limit)

    return {
        "status": status,
        "history": history,
    }


def get_transactional_message_status(
    message_id: int,
) -> dict[str, Any] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    client = DatamailerClient(config)

    try:
        return client.transactional_message_status(message_id)
    except requests.RequestException:
        logger.exception(
            "Datamailer transactional message status lookup failed"
        )
        if config.strict:
            raise
        return None
