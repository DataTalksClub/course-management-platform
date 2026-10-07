import logging
from uuid import uuid4

import requests

from course_management.datamailer_outbox import (
    DatamailerOutboxEventData,
    enqueue_datamailer_outbox_event,
)

from .client import DatamailerClient, DatamailerConfig
from .preference_categories import (
    email_preference_category_tags,
    email_preference_payloads,
    email_preference_values_from_response,
)

logger = logging.getLogger(__name__)


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


def _contact_preferences_response(user, email, config):
    client = DatamailerClient(config)
    try:
        category_tags = email_preference_category_tags()
        return client.contacts.contact_preferences(
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


def enqueue_email_preference_update_for_user(
    user,
    values: dict[str, bool],
) -> bool:
    """Queue a preference update so Relay blips cannot fail user requests.

    The scheduled outbox processor applies the update with retries; Relay
    being down delays it instead of surfacing a 5xx or losing the choice.
    """
    context = _datamailer_user_context(user)
    if context is None:
        return False

    categories = email_preference_payloads(values)
    if not categories:
        return False

    email, config = context
    enqueue_datamailer_outbox_event(
        DatamailerOutboxEventData(
            event_type="contact.update_preferences",
            idempotency_key=(
                f"contact.update_preferences:user:{user.pk}:{uuid4()}"
            ),
            ordering_key=f"user:{user.pk}",
            payload={
                "email": email,
                "categories": categories,
                "audience": config.audience,
                "client": config.client,
                "user_id": user.pk,
            },
        )
    )
    return True
