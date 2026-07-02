import logging

import requests

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


def _log_preference_update_error(user):
    logger.exception(
        "Datamailer preference update failed for user_id=%s",
        user.pk,
    )


def _send_email_preference_update(user, email, config, categories):
    client = DatamailerClient(config)
    try:
        client.contacts.update_contact_preferences(email, categories)
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

    categories = email_preference_payloads(values)
    if not categories:
        return False

    email, config = context
    return _send_email_preference_update(user, email, config, categories)
