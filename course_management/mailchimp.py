import hashlib
from dataclasses import dataclass
from typing import Any

import requests
from django.conf import settings

from courses.models import CourseRegistration


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
    """Retired compatibility hook.

    Datamailer owns course-registration audience sync. Keep this function
    harmless while older manual scripts/imports still exist.
    """
    tag = registration.campaign.selected_mailchimp_tag()
    registration.mailchimp_sync_status = (
        CourseRegistration.MailchimpSyncStatus.SKIPPED
    )
    registration.mailchimp_tag_used = tag
    registration.mailchimp_error = ""
    registration.save(
        update_fields=[
            "mailchimp_sync_status",
            "mailchimp_tag_used",
            "mailchimp_error",
            "updated_at",
        ]
    )
