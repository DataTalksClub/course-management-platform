import logging
from dataclasses import dataclass
from typing import Any

import requests

from .client import DatamailerClient, DatamailerConfig

logger = logging.getLogger(__name__)

__all__ = [
    "EMAIL_PREFERENCE_CATEGORIES",
    "email_preference_category_tags",
    "email_preference_values_from_response",
    "get_email_preferences_for_user",
    "update_email_preferences_for_user",
]

EMAIL_PREFERENCE_CATEGORIES = {
    "email_submission_confirmations": {
        "tag": "submission-results",
        "label": "Homework and project submissions",
        "description": (
            "Sends confirmation and score emails after you submit homework "
            "or a project."
        ),
    },
    "email_deadline_reminders": {
        "tag": "deadline-reminders",
        "label": "Deadline reminders",
        "description": (
            "Sends reminders when homework or peer review deadlines are "
            "within 24 hours and you have not submitted. For projects, "
            "sends one reminder one week before the deadline encouraging "
            "half-finished submissions, and another one day before the "
            "deadline because submissions will close soon. For peer "
            "reviews, sends links to unfinished reviews and explains that "
            "peer review completion is mandatory for project completion "
            "and receiving a certificate."
        ),
    },
    "email_course_updates": {
        "tag": "course-updates",
        "label": "General course-related emails",
        "description": (
            "Sends general course and workshop messages, such as course "
            "start announcements and workshop start announcements."
        ),
    },
}


@dataclass(frozen=True)
class EmailPreferencePayloadData:
    field: str
    enabled: bool


def email_preference_category_tags() -> list[str]:
    tags = []
    categories = EMAIL_PREFERENCE_CATEGORIES.values()
    for category in categories:
        tags.append(category["tag"])
    return tags


def _normalized_user_email(user) -> str:
    email = user.email or ""
    stripped_email = email.strip()
    normalized_email = stripped_email.lower()
    return normalized_email


def _datamailer_user_context(user):
    email = _normalized_user_email(user)
    if not email:
        return None

    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    return email, config


def _response_categories_by_tag(response):
    categories_by_tag = {}
    categories = response.get("categories", [])
    for category in categories:
        if not isinstance(category, dict):
            continue
        tag = category.get("tag")
        categories_by_tag[tag] = category
    return categories_by_tag


def _enabled_preference_value(category, by_tag):
    item = by_tag.get(category["tag"])
    enabled = None
    if item is not None:
        enabled = item.get("enabled")
    if not isinstance(enabled, bool):
        return None

    return enabled


def email_preference_values_from_response(
    response: dict[str, Any] | None,
) -> dict[str, bool]:
    if not response:
        return {}

    by_tag = _response_categories_by_tag(response)
    values = {}
    for field, category in EMAIL_PREFERENCE_CATEGORIES.items():
        enabled = _enabled_preference_value(category, by_tag)
        if enabled is not None:
            values[field] = enabled
    return values


def _email_preference_payload(
    data: EmailPreferencePayloadData,
) -> dict[str, Any] | None:
    category = EMAIL_PREFERENCE_CATEGORIES.get(data.field)
    if category is None:
        return None
    enabled = bool(data.enabled)
    return {
        "tag": category["tag"],
        "label": category["label"],
        "enabled": enabled,
    }


def _email_preference_payloads(
    values: dict[str, bool],
) -> list[dict[str, Any]]:
    payloads = []
    for field, enabled in values.items():
        payload_data = EmailPreferencePayloadData(field, enabled)
        payload = _email_preference_payload(payload_data)
        if payload is not None:
            payloads.append(payload)
    return payloads


def _contact_preferences_response(user, email, config):
    client = DatamailerClient(config)
    try:
        category_tags = email_preference_category_tags()
        return client.contact_preferences(
            email,
            category_tags=category_tags,
        )
    except requests.RequestException:
        logger.exception(
            "Datamailer preference lookup failed for user_id=%s",
            user.pk,
        )
        if config.strict:
            raise
        return None


def get_email_preferences_for_user(user) -> dict[str, bool] | None:
    context = _datamailer_user_context(user)
    if context is None:
        return None

    email, config = context
    response = _contact_preferences_response(user, email, config)
    if response is None:
        return None
    return email_preference_values_from_response(response)


def _log_preference_update_error(user):
    logger.exception(
        "Datamailer preference update failed for user_id=%s",
        user.pk,
    )


def _send_email_preference_update(user, email, config, categories):
    client = DatamailerClient(config)
    try:
        client.update_contact_preferences(email, categories)
    except requests.RequestException:
        _log_preference_update_error(user)
        if config.strict:
            raise
        return False
    return True


def update_email_preferences_for_user(
    user,
    values: dict[str, bool],
) -> bool:
    context = _datamailer_user_context(user)
    if context is None:
        return False

    categories = _email_preference_payloads(values)
    if not categories:
        return False

    email, config = context
    return _send_email_preference_update(user, email, config, categories)
