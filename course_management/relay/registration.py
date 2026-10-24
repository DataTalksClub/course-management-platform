"""Registration contacts and memberships sent to Relay via the outbox.

Shared payload builders and the durable dispatcher retain their historical
package names. They read only RELAY_* configuration.
"""

import logging

from course_management.datamailer.client import validate_relay_config
from course_management.datamailer.payloads.registration_contacts import (
    registration_contact_payload,
)
from course_management.datamailer.payloads.registration_members import (
    registration_recipient_list_payload,
)
from course_management.datamailer.sync.membership_events import (
    ContactMembershipSyncData,
    sync_contact_and_membership,
)

logger = logging.getLogger(__name__)


def sync_registration_to_relay(registration) -> None:
    """Log sync failures without rejecting an already saved registration."""
    try:
        valid, reason, config = validate_relay_config()
        if not valid or config is None:
            logger.error(
                "Relay registration sync failed registration_id=%s: %s",
                registration.pk,
                reason,
            )
            return

        contact_payload = registration_contact_payload(registration)
        list_payload = registration_recipient_list_payload(registration)
        if contact_payload is None or list_payload is None:
            logger.error(
                "Relay registration sync failed registration_id=%s: "
                "registration_payload_missing",
                registration.pk,
            )
            return

        sync_contact_and_membership(
            ContactMembershipSyncData(
                contact_payload=contact_payload,
                list_payload=list_payload,
                label="registration",
                obj=registration,
            )
        )
    except Exception:
        # Runs after commit: a downstream failure must not turn a successful
        # registration into a 500. The dispatcher retains transport retries.
        logger.exception(
            "Relay registration sync failed registration_id=%s",
            registration.pk,
        )
