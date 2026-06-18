import logging
import re
from dataclasses import dataclass
from typing import Any

import requests
from django.conf import settings

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

    def upsert_contact(self, payload: dict[str, Any]) -> dict[str, Any] | None:
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


def contact_payload_for_user(user, course=None) -> dict[str, Any] | None:
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


def send_transactional_email(payload: dict[str, Any]) -> dict[str, Any] | None:
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


def get_email_status(email: str, *, limit: int = 25) -> dict[str, Any] | None:
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
        logger.exception("Datamailer transactional message status lookup failed")
        if config.strict:
            raise
        return None
