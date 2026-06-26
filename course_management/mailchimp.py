import hashlib
import logging
from dataclasses import dataclass
from typing import Any

import requests
from django.conf import settings
from django.utils import timezone

from courses.models import CourseRegistration

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MailchimpConfig:
    token: str
    list_id: str
    strict: bool = False

    @classmethod
    def from_settings(cls) -> "MailchimpConfig | None":
        token = getattr(settings, "MAILCHIMP_TOKEN", "")
        list_id = getattr(settings, "MAILCHIMP_LIST_ID", "")
        if not token or not list_id:
            return None
        return cls(
            token=token,
            list_id=list_id,
            strict=getattr(settings, "MAILCHIMP_STRICT", False),
        )

    @property
    def data_center(self):
        if "-" not in self.token:
            return ""
        return self.token.rsplit("-", 1)[1]


class MailchimpClient:
    def __init__(
        self,
        config: MailchimpConfig,
        session: requests.Session | None = None,
    ):
        self.config = config
        self.session = session or requests.Session()

    def request(self, method: str, path: str, *, json=None):
        url = f"https://{self.config.data_center}.api.mailchimp.com/3.0{path}"
        response = self.session.request(
            method,
            url,
            auth=("anystring", self.config.token),
            headers={"Content-Type": "application/json"},
            json=json,
            timeout=10,
        )
        response.raise_for_status()
        if not response.content:
            return None
        return response.json()

    def upsert_member(self, email: str, merge_fields: dict[str, Any]):
        subscriber_hash = hashlib.md5(
            email.strip().lower().encode("utf-8")
        ).hexdigest()
        path = (
            f"/lists/{self.config.list_id}/members/{subscriber_hash}"
        )
        payload = {
            "email_address": email,
            "status_if_new": "subscribed",
            "merge_fields": merge_fields,
        }
        return subscriber_hash, self.request("PUT", path, json=payload)

    def add_member_tag(self, subscriber_hash: str, tag: str):
        path = (
            f"/lists/{self.config.list_id}/members/{subscriber_hash}/tags"
        )
        payload = {"tags": [{"name": tag, "status": "active"}]}
        return self.request("POST", path, json=payload)


def sync_registration_to_mailchimp(registration: CourseRegistration) -> None:
    config = MailchimpConfig.from_settings()
    tag = registration.campaign.selected_mailchimp_tag()

    if config is None or not tag or not registration.accepted_newsletter:
        registration.mailchimp_sync_status = (
            CourseRegistration.MailchimpSyncStatus.SKIPPED
        )
        registration.mailchimp_tag_used = tag or ""
        registration.mailchimp_error = ""
        registration.save(
            update_fields=[
                "mailchimp_sync_status",
                "mailchimp_tag_used",
                "mailchimp_error",
                "updated_at",
            ]
        )
        return

    client = MailchimpClient(config)
    registration.mailchimp_sync_status = (
        CourseRegistration.MailchimpSyncStatus.PENDING
    )
    registration.mailchimp_tag_used = tag
    registration.save(
        update_fields=[
            "mailchimp_sync_status",
            "mailchimp_tag_used",
            "updated_at",
        ]
    )

    try:
        subscriber_hash, _response = client.upsert_member(
            registration.email_normalized,
            {"FNAME": registration.name[:255]},
        )
        client.add_member_tag(subscriber_hash, tag)
    except requests.RequestException as exc:
        logger.exception(
            "Mailchimp registration sync failed for registration_id=%s",
            registration.pk,
        )
        registration.mailchimp_sync_status = (
            CourseRegistration.MailchimpSyncStatus.FAILED
        )
        registration.mailchimp_error = str(exc)
        registration.save(
            update_fields=[
                "mailchimp_sync_status",
                "mailchimp_error",
                "updated_at",
            ]
        )
        if config.strict:
            raise
        return

    registration.mailchimp_sync_status = (
        CourseRegistration.MailchimpSyncStatus.SYNCED
    )
    registration.mailchimp_synced_at = timezone.now()
    registration.mailchimp_error = ""
    registration.save(
        update_fields=[
            "mailchimp_sync_status",
            "mailchimp_synced_at",
            "mailchimp_error",
            "updated_at",
        ]
    )
