import logging
from typing import Any

import requests


from .client import DatamailerClient, DatamailerConfig

logger = logging.getLogger(__name__)

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


def email_preference_category_tags() -> list[str]:
    return [
        category["tag"]
        for category in EMAIL_PREFERENCE_CATEGORIES.values()
    ]

def email_preference_values_from_response(
    response: dict[str, Any] | None,
) -> dict[str, bool]:
    if not response:
        return {}
    by_tag = {
        category.get("tag"): category
        for category in response.get("categories", [])
        if isinstance(category, dict)
    }
    values = {}
    for field, category in EMAIL_PREFERENCE_CATEGORIES.items():
        item = by_tag.get(category["tag"])
        if item is not None and isinstance(item.get("enabled"), bool):
            values[field] = item["enabled"]
    return values

def get_email_preferences_for_user(user) -> dict[str, bool] | None:
    email = (user.email or "").strip().lower()
    if not email:
        return None
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    client = DatamailerClient(config)
    try:
        response = client.contact_preferences(
            email,
            category_tags=email_preference_category_tags(),
        )
    except requests.RequestException:
        logger.exception(
            "Datamailer preference lookup failed for user_id=%s",
            user.pk,
        )
        if config.strict:
            raise
        return None
    return email_preference_values_from_response(response)

def update_email_preferences_for_user(
    user,
    values: dict[str, bool],
) -> bool:
    email = (user.email or "").strip().lower()
    if not email:
        return False
    config = DatamailerConfig.from_settings()
    if config is None:
        return False

    categories = []
    for field, enabled in values.items():
        category = EMAIL_PREFERENCE_CATEGORIES.get(field)
        if category is None:
            continue
        categories.append(
            {
                "tag": category["tag"],
                "label": category["label"],
                "enabled": bool(enabled),
            }
        )
    if not categories:
        return False

    client = DatamailerClient(config)
    try:
        client.update_contact_preferences(email, categories)
    except requests.RequestException:
        logger.exception(
            "Datamailer preference update failed for user_id=%s",
            user.pk,
        )
        if config.strict:
            raise
        return False
    return True
