from typing import Any

from ..client import DatamailerConfig
from ..keys import contact_tags_for_course
from .registration_common import registration_email


def registration_contact_tags(registration) -> list[str]:
    course = registration.course
    if course is None:
        return []

    return contact_tags_for_course(course)


def registration_contact_payload(registration) -> dict[str, Any] | None:
    email = registration_email(registration)
    if not email:
        return None

    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    tags = registration_contact_tags(registration)
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
