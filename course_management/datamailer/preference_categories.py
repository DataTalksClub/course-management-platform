from typing import Any

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
    tags = []
    categories = EMAIL_PREFERENCE_CATEGORIES.values()
    for category in categories:
        tags.append(category["tag"])
    return tags


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


def email_preference_payload(
    field: str,
    enabled: bool,
) -> dict[str, Any] | None:
    category = EMAIL_PREFERENCE_CATEGORIES.get(field)
    if category is None:
        return None
    enabled_value = bool(enabled)
    return {
        "tag": category["tag"],
        "label": category["label"],
        "enabled": enabled_value,
    }


def email_preference_payloads(
    values: dict[str, bool],
) -> list[dict[str, Any]]:
    payloads = []
    for field, enabled in values.items():
        payload = email_preference_payload(field, enabled)
        if payload is not None:
            payloads.append(payload)
    return payloads
