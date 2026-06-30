import logging
from typing import Any

import requests

from .client import DatamailerClient, DatamailerConfig

logger = logging.getLogger(__name__)


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
