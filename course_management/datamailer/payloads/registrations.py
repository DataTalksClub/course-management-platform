from dataclasses import dataclass
from typing import Any

from django.urls import reverse

from course_management import email_templates
from courses.registration import render_markdown

from ..client import DatamailerConfig, public_url
from ..keys import contact_tags_for_course, registration_list_key
from ..preferences import EMAIL_PREFERENCE_CATEGORIES
from .base import (
    RecipientListMemberPayload,
    RecipientListMemberPayloadData,
    recipient_list_member_payload,
)


@dataclass(frozen=True)
class RegistrationConfirmationPayloadData:
    config: DatamailerConfig
    registration: object
    campaign: object
    course: object
    urls: dict[str, str]
    email: str


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
    return {
        "subject": campaign.title,
        "preview_text": campaign.meta_description[:255],
        "html_body": render_markdown(data.body_text),
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


def registration_email(registration) -> str:
    return (
        (registration.email_normalized or registration.email or "")
        .strip()
        .lower()
    )


def registration_confirmation_urls(campaign, course) -> dict[str, str]:
    registration_path = reverse(
        "registration_campaign",
        kwargs={"campaign_slug": campaign.slug},
    )
    course_url = ""
    if course is not None:
        course_path = reverse("course", kwargs={"course_slug": course.slug})
        course_url = public_url(course_path)
    registration_url = public_url(registration_path)
    profile_path = reverse("account_settings")
    profile_url = public_url(profile_path)
    return {
        "registration_url": registration_url,
        "course_url": course_url,
        "profile_url": profile_url,
    }


def registration_confirmation_metadata(registration, campaign, course):
    course_slug = ""
    if course is not None:
        course_slug = course.slug
    return {
        "source": "course-management-platform",
        "event": "course_registration",
        "registration_id": registration.pk,
        "campaign_slug": campaign.slug,
        "course_slug": course_slug,
        "preference_key": "email_course_updates",
        "cmp_preference_key": "email_course_updates",
    }


def registration_confirmation_course_context(course):
    context = {
        "course_title": "",
        "course_slug": "",
    }
    if course is not None:
        context["course_title"] = course.title
        context["course_slug"] = course.slug
    return context


def registration_confirmation_context(registration, campaign, course, urls):
    profile_url = urls["profile_url"]
    course_context = registration_confirmation_course_context(course)
    context = {
        "email_subject": f"Registration confirmed: {campaign.title}",
        "campaign_title": campaign.title,
        "campaign_slug": campaign.slug,
        "registration_id": registration.pk,
        "registration_url": urls["registration_url"],
        "course_url": urls["course_url"],
        "profile_url": profile_url,
        "intro_text": (
            f"Your registration for {campaign.title} is confirmed."
        ),
        "notification_category": "course-related emails",
        "notification_footer": (
            "You are receiving this because course-related emails are "
            "enabled."
        ),
        "notification_footer_text": (
            "If you don't want to receive course-related emails, turn "
            f"them off in your profile: {profile_url}"
        ),
    }
    context.update(course_context)
    return context


def registration_confirmation_payload(registration) -> dict[str, Any] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    email = registration_email(registration)
    if not email:
        return None

    campaign = registration.campaign
    course = registration.course
    urls = registration_confirmation_urls(campaign, course)
    payload_data = RegistrationConfirmationPayloadData(
        config=config,
        registration=registration,
        campaign=campaign,
        course=course,
        urls=urls,
        email=email,
    )
    return registration_confirmation_payload_from_data(payload_data)


def registration_confirmation_payload_from_data(
    data: RegistrationConfirmationPayloadData,
) -> dict[str, Any]:
    return {
        "audience": data.config.audience,
        "client": data.config.client,
        "email": data.email,
        "template_key": email_templates.REGISTRATION_CONFIRMATION,
        "category_tag": EMAIL_PREFERENCE_CATEGORIES[
            "email_course_updates"
        ]["tag"],
        "idempotency_key": (
            f"registration-confirmation:{data.registration.pk}"
        ),
        "context": registration_confirmation_context(
            data.registration,
            data.campaign,
            data.course,
            data.urls,
        ),
        "metadata": registration_confirmation_metadata(
            data.registration,
            data.campaign,
            data.course,
        ),
    }


def registration_contact_tags(registration) -> list[str]:
    course = registration.course
    if course is None:
        return []

    return contact_tags_for_course(course)


def registration_contact_payload(registration) -> dict[str, Any] | None:
    email = registration_email(registration)
    if not email:
        return None

    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    return {
        "email": email,
        "audience": config.audience,
        "client": config.client,
        "status": "subscribed",
        "verified": True,
        "email_validation": {
            "status": "externally_validated",
        },
        "tags": registration_contact_tags(registration),
    }


def registration_recipient_list_payload(
    registration,
) -> RecipientListMemberPayload | None:
    email = registration_email(registration)
    if not email:
        return None

    list_key = registration_list_key(registration)
    source_object_key = f"registration:{registration.pk}"
    payload_data = RecipientListMemberPayloadData(
        list_type="registrants",
        list_name=registration_recipient_list_name(registration),
        email=email,
        source_object_key=source_object_key,
        metadata=registration_recipient_metadata(registration),
    )
    payload = recipient_list_member_payload(payload_data)
    if payload is None:
        return None
    return RecipientListMemberPayload(
        list_key=list_key,
        source_object_key=source_object_key,
        payload=payload,
    )


def registration_recipient_list_name(registration) -> str:
    course = registration.course
    if course is not None:
        title = course.title
    else:
        title = registration.campaign.title
    return f"{title} registrants"


def registration_recipient_metadata(registration) -> dict[str, Any]:
    course = registration.course
    course_slug = ""
    if course is not None:
        course_slug = course.slug
    registered_at = ""
    if registration.created_at:
        registered_at = registration.created_at.isoformat()
    return {
        "registration_id": registration.pk,
        "campaign_slug": registration.campaign.slug,
        "course_slug": course_slug,
        "user_id": registration.user_id,
        "registered_at": registered_at,
        "country": registration.country,
        "region": registration.region,
        "role": registration.role,
    }
