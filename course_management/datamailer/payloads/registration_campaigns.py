from dataclasses import dataclass
from typing import Any

from django.urls import reverse

from courses.registration import render_markdown

from ..client import public_url
from ..preferences import EMAIL_PREFERENCE_CATEGORIES


@dataclass(frozen=True)
class RegistrationCampaignPayloadData:
    campaign: object
    body_text: str
    registration_url: str


def registration_campaign_datamailer_payload(campaign) -> dict[str, Any]:
    payload_data = registration_campaign_payload_data(campaign)
    payload: dict[str, Any] = registration_campaign_base_payload(payload_data)
    if campaign.current_course_id:
        payload["recipient_list_key"] = campaign.current_course.slug
        metadata = payload["metadata"]
        metadata["course_slug"] = campaign.current_course.slug
        metadata["course_title"] = campaign.current_course.title
    return payload


def registration_campaign_payload_data(
    campaign,
) -> RegistrationCampaignPayloadData:
    body_text = (
        campaign.marketing_markdown.strip()
        or campaign.meta_description.strip()
        or campaign.title
    )
    public_path = reverse(
        "registration_campaign",
        kwargs={"campaign_slug": campaign.slug},
    )
    registration_url = public_url(public_path)
    return RegistrationCampaignPayloadData(
        campaign=campaign,
        body_text=body_text,
        registration_url=registration_url,
    )


def registration_campaign_base_payload(
    data: RegistrationCampaignPayloadData,
) -> dict[str, Any]:
    campaign = data.campaign
    html_body = render_markdown(data.body_text)
    return {
        "subject": campaign.title,
        "preview_text": campaign.meta_description[:255],
        "html_body": html_body,
        "text_body": data.body_text,
        "category_tag": EMAIL_PREFERENCE_CATEGORIES[
            "email_course_updates"
        ]["tag"],
        "include_tags": [],
        "exclude_tags": [],
        "metadata": {
            "cmp_registration_campaign_slug": campaign.slug,
            "registration_url": data.registration_url,
        },
    }
