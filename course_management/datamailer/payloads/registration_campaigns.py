from dataclasses import dataclass
from typing import Any

from courses.registration import render_markdown

from ..preference_categories import EMAIL_PREFERENCE_CATEGORIES
from .urls import public_route_url


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
    registration_kwargs = {"campaign_slug": campaign.slug}
    registration_url = public_route_url(
        "registration_campaign",
        registration_kwargs,
    )
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
