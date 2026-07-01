import logging

import requests

from course_management.datamailer_outbox import (
    DatamailerOutboxEventData,
    enqueue_datamailer_outbox_event,
)

from ..client import DatamailerClient, DatamailerConfig
from ..payloads import contact_payload_for_user


logger = logging.getLogger(__name__)


def payload_with_configured_from_email(payload, config):
    if config.from_email and "from_email" not in payload:
        return payload | {"from_email": config.from_email}
    return payload


def handle_contact_sync_error(config, user):
    logger.exception(
        "Datamailer contact sync failed for user_id=%s",
        user.pk,
    )
    if config.strict:
        raise


def sync_contact(user, course=None) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    payload = contact_payload_for_user(user, course=course)
    if payload is None:
        return

    client = DatamailerClient(config)
    payload = payload_with_configured_from_email(payload, config)

    try:
        client.upsert_contact(payload)
    except requests.RequestException:
        handle_contact_sync_error(config, user)


def erase_contact_from_datamailer(
    user=None, *, user_id=None, email=None
) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    user_id, email = contact_erase_target(
        user, user_id=user_id, email=email
    )
    if not email:
        return

    ordering_key = contact_erase_ordering_key(user_id, email)
    enqueue_contact_erase_event(
        config,
        user_id=user_id,
        email=email,
        ordering_key=ordering_key,
    )


def contact_erase_target(user, *, user_id, email):
    user_id = contact_erase_user_id(user, user_id)
    email = contact_erase_email(user, email)
    return user_id, email


def contact_erase_user_id(user, user_id):
    if user_id is None and user is not None:
        return user.pk
    return user_id


def contact_erase_email(user, email):
    if email is None and user is not None:
        email = user.email
    email_value = email or ""
    stripped_email = email_value.strip()
    normalized_email = stripped_email.lower()
    return normalized_email


def contact_erase_ordering_key(user_id, email):
    if user_id is not None:
        return f"user:{user_id}"
    return f"email:{email}"


def enqueue_contact_erase_event(config, *, user_id, email, ordering_key):
    event_data = DatamailerOutboxEventData(
        event_type="contact.erase",
        idempotency_key=f"contact.erase:{ordering_key}:{email}",
        ordering_key=ordering_key,
        payload={
            "email": email,
            "audience": config.audience,
            "client": config.client,
            "user_id": user_id,
        },
    )
    enqueue_datamailer_outbox_event(event_data)
