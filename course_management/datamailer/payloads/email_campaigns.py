from dataclasses import dataclass
from typing import Any

from courses.registration import render_markdown

from ..client import DatamailerConfig
from ..preference_categories import EMAIL_PREFERENCE_CATEGORIES
from .score_notifications import add_from_email_if_configured
from .urls import public_route_url


@dataclass(frozen=True)
class EmailCampaignPayloadData:
    email_campaign: object
    registration_url: str


def email_campaign_datamailer_payload(email_campaign) -> dict[str, Any]:
    payload_data = email_campaign_payload_data(email_campaign)
    payload: dict[str, Any] = email_campaign_base_payload(payload_data)
    registration_campaign = email_campaign.registration_campaign
    if registration_campaign.current_course_id:
        course = registration_campaign.current_course
        payload["recipient_list_key"] = course.slug
        metadata = payload["metadata"]
        metadata["course_slug"] = course.slug
        metadata["course_title"] = course.title
    config = DatamailerConfig.from_settings()
    if config is not None:
        payload = add_from_email_if_configured(payload, config)
    return payload


def email_campaign_payload_data(email_campaign) -> EmailCampaignPayloadData:
    registration_kwargs = {
        "campaign_slug": email_campaign.registration_campaign.slug
    }
    registration_url = public_route_url(
        "registration_campaign",
        registration_kwargs,
    )
    return EmailCampaignPayloadData(
        email_campaign=email_campaign,
        registration_url=registration_url,
    )


def email_campaign_base_payload(
    data: EmailCampaignPayloadData,
) -> dict[str, Any]:
    email_campaign = data.email_campaign
    registration_campaign = email_campaign.registration_campaign
    html_body = render_markdown(email_campaign.body_markdown)
    return {
        "subject": email_campaign.subject,
        "preview_text": email_campaign.preview_text[:255],
        "html_body": html_body,
        "text_body": email_campaign.body_markdown,
        "category_tag": EMAIL_PREFERENCE_CATEGORIES[
            "email_course_updates"
        ]["tag"],
        "include_tags": [],
        "exclude_tags": [],
        "metadata": {
            "cmp_registration_campaign_slug": registration_campaign.slug,
            "cmp_email_campaign_id": email_campaign.pk,
            "registration_url": data.registration_url,
        },
    }
