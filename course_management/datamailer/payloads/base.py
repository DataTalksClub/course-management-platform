from dataclasses import dataclass
from typing import Any

from django.urls import reverse

from course_management import email_templates
from courses.registration import render_markdown

from ..client import DatamailerConfig, public_url
from ..keys import (
    contact_tags_for_course,
    course_enrolled_list_key,
    course_family_slug,
    homework_submitters_list_key,
    project_submitters_list_key,
    registration_list_key,
)
from ..preferences import EMAIL_PREFERENCE_CATEGORIES

@dataclass(frozen=True)
class RecipientListMemberPayloadData:
    list_type: str
    list_name: str
    email: str
    source_object_key: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class RecipientListMemberPayload:
    list_key: str
    source_object_key: str
    payload: dict[str, Any]


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


def contact_base_custom_fields(user) -> dict[str, str]:
    return {
        "course_platform_user_id": str(user.pk),
        "username": user.username or "",
    }


def contact_course_custom_fields(course) -> dict[str, str]:
    return {
        "course_slug": course.slug,
        "course_family_slug": course_family_slug(course),
        "course_cohort_slug": course.slug,
        "course_title": course.title,
    }


def contact_payload_tags_and_fields(user, course):
    tags = []
    custom_fields = contact_base_custom_fields(user)

    if course is not None:
        course_tags = contact_tags_for_course(course)
        tags.extend(course_tags)

        course_custom_fields = contact_course_custom_fields(course)
        custom_fields.update(course_custom_fields)

    return tags, custom_fields


def contact_payload_for_user(
    user, course=None
) -> dict[str, Any] | None:
    email = (user.email or "").strip().lower()
    if not email:
        return None

    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    tags, custom_fields = contact_payload_tags_and_fields(user, course)

    return {
        "email": email,
        "audience": config.audience,
        "client": config.client,
        "status": "subscribed",
        "verified": True,
        "email_validation": {
            "status": "externally_validated",
        },
        "tags": tags,
        "custom_fields": custom_fields,
    }


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
    return RegistrationCampaignPayloadData(
        campaign=campaign,
        body_text=body_text,
        registration_url=public_url(public_path),
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


def _registration_email(registration) -> str:
    return (
        (registration.email_normalized or registration.email or "")
        .strip()
        .lower()
    )


def _registration_confirmation_urls(campaign, course) -> dict[str, str]:
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


def _registration_confirmation_metadata(registration, campaign, course):
    return {
        "source": "course-management-platform",
        "event": "course_registration",
        "registration_id": registration.pk,
        "campaign_slug": campaign.slug,
        "course_slug": course.slug if course is not None else "",
        "preference_key": "email_course_updates",
        "cmp_preference_key": "email_course_updates",
    }


def _registration_confirmation_context(registration, campaign, course, urls):
    profile_url = urls["profile_url"]
    return {
        "email_subject": f"Registration confirmed: {campaign.title}",
        "campaign_title": campaign.title,
        "campaign_slug": campaign.slug,
        "course_title": course.title if course is not None else "",
        "course_slug": course.slug if course is not None else "",
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


def registration_confirmation_payload(registration) -> dict[str, Any] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    email = _registration_email(registration)
    if not email:
        return None

    campaign = registration.campaign
    course = registration.course
    urls = _registration_confirmation_urls(campaign, course)
    payload_data = RegistrationConfirmationPayloadData(
        config=config,
        registration=registration,
        campaign=campaign,
        course=course,
        urls=urls,
        email=email,
    )
    return _registration_confirmation_payload(payload_data)


def _registration_confirmation_payload(
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
        "context": _registration_confirmation_context(
            data.registration,
            data.campaign,
            data.course,
            data.urls,
        ),
        "metadata": _registration_confirmation_metadata(
            data.registration,
            data.campaign,
            data.course,
        ),
    }


def _registration_contact_tags(registration) -> list[str]:
    course = registration.course
    if course is None:
        return []

    return contact_tags_for_course(course)


def registration_contact_payload(registration) -> dict[str, Any] | None:
    email = _registration_email(registration)
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
        "tags": _registration_contact_tags(registration),
    }


def recipient_list_member_payload(data) -> dict[str, Any] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    return {
        "audience": config.audience,
        "client": config.client,
        "list": {
            "type": data.list_type,
            "name": data.list_name,
            "metadata": data.metadata,
        },
        "member": {
            "email": data.email.strip().lower(),
            "status": "active",
            "metadata": data.metadata
            | {"source_object_key": data.source_object_key},
        },
    }

def removed_recipient_list_member_payload(
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        **payload,
        "member": {
            **payload["member"],
            "status": "removed",
        },
    }

def registration_recipient_list_payload(
    registration,
) -> RecipientListMemberPayload | None:
    email = _registration_email(registration)
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
    title = course.title if course is not None else registration.campaign.title
    return f"{title} registrants"


def registration_recipient_metadata(registration) -> dict[str, Any]:
    course = registration.course
    return {
        "registration_id": registration.pk,
        "campaign_slug": registration.campaign.slug,
        "course_slug": course.slug if course is not None else "",
        "user_id": registration.user_id,
        "registered_at": registration.created_at.isoformat()
        if registration.created_at
        else "",
        "country": registration.country,
        "region": registration.region,
        "role": registration.role,
    }


def enrollment_recipient_metadata(enrollment) -> dict[str, Any]:
    return {
        "enrollment_id": enrollment.pk,
        "user_id": enrollment.student_id,
        "course_slug": enrollment.course.slug,
        "display_name": enrollment.display_name,
    }


def enrollment_recipient_list_payload(
    enrollment,
) -> RecipientListMemberPayload | None:
    email = (enrollment.student.email or "").strip().lower()
    if not email:
        return None

    course = enrollment.course
    list_key = course_enrolled_list_key(course)
    source_object_key = f"user:{enrollment.student_id}"
    payload_data = RecipientListMemberPayloadData(
        list_type="custom",
        list_name=f"{course.title} enrolled learners",
        email=email,
        source_object_key=source_object_key,
        metadata=enrollment_recipient_metadata(enrollment),
    )
    payload = recipient_list_member_payload(payload_data)
    if payload is None:
        return None
    return RecipientListMemberPayload(
        list_key=list_key,
        source_object_key=source_object_key,
        payload=payload,
    )

def homework_submission_recipient_list_payload(
    submission,
) -> RecipientListMemberPayload | None:
    email = (submission.student.email or "").strip().lower()
    if not email:
        return None

    homework = submission.homework
    course = homework.course
    list_key = homework_submitters_list_key(homework)
    source_object_key = f"homework-submission:{submission.pk}"
    payload_data = RecipientListMemberPayloadData(
        list_type="homework_submitters",
        list_name=f"{course.title} {homework.title} submitters",
        email=email,
        source_object_key=source_object_key,
        metadata=homework_submission_metadata(submission),
    )
    payload = recipient_list_member_payload(payload_data)
    if payload is None:
        return None
    return RecipientListMemberPayload(
        list_key=list_key,
        source_object_key=source_object_key,
        payload=payload,
    )


def homework_submission_metadata(submission) -> dict[str, Any]:
    homework = submission.homework
    course = homework.course
    return {
        "submission_id": submission.pk,
        "user_id": submission.student_id,
        "course_slug": course.slug,
        "homework_slug": homework.slug,
        "submitted_at": submission.submitted_at.isoformat()
        if submission.submitted_at
        else "",
        "questions_score": submission.questions_score,
        "learning_in_public_score": submission.learning_in_public_score,
        "faq_score": submission.faq_score,
        "total_score": submission.total_score,
        "homework_url": homework_public_url(homework),
    }


def homework_public_url(homework):
    homework_path = reverse(
        "homework",
        kwargs={
            "course_slug": homework.course.slug,
            "homework_slug": homework.slug,
        },
    )
    homework_url = public_url(homework_path)
    return homework_url


def project_submission_metadata(submission) -> dict[str, Any]:
    return {
        **project_submission_identity_metadata(submission),
        **project_submission_score_metadata(submission),
        **project_submission_source_metadata(submission),
        **project_submission_status_metadata(submission),
    }


def project_submission_identity_metadata(submission) -> dict[str, Any]:
    project = submission.project
    course = project.course
    return {
        "submission_id": submission.pk,
        "user_id": submission.student_id,
        "course_slug": course.slug,
        "project_slug": project.slug,
        "submitted_at": submission.submitted_at.isoformat()
        if submission.submitted_at
        else "",
    }


def project_submission_score_metadata(submission) -> dict[str, Any]:
    return {
        "project_score": submission.project_score,
        "project_learning_in_public_score": (
            submission.project_learning_in_public_score
        ),
        "project_faq_score": submission.project_faq_score,
        "peer_review_score": submission.peer_review_score,
        "peer_review_learning_in_public_score": (
            submission.peer_review_learning_in_public_score
        ),
        "total_score": submission.total_score,
    }


def project_submission_source_metadata(submission) -> dict[str, Any]:
    return {
        "github_link": submission.github_link,
        "commit_id": submission.commit_id,
        "faq_contribution_url": submission.faq_contribution_url or "",
        "project_url": project_public_url(submission.project),
    }


def project_submission_status_metadata(submission) -> dict[str, Any]:
    return {
        "reviewed_enough_peers": submission.reviewed_enough_peers,
        "passed": submission.passed,
    }


def project_public_url(project):
    project_path = reverse(
        "project",
        kwargs={
            "course_slug": project.course.slug,
            "project_slug": project.slug,
        },
    )
    project_url = public_url(project_path)
    return project_url


def project_submission_recipient_list_payload(
    submission,
) -> RecipientListMemberPayload | None:
    email = (submission.student.email or "").strip().lower()
    if not email:
        return None

    project = submission.project
    course = project.course
    list_key = project_submitters_list_key(project)
    source_object_key = f"project-submission:{submission.pk}"
    payload_data = RecipientListMemberPayloadData(
        list_type="project_submitters",
        list_name=f"{course.title} {project.title} submitters",
        email=email,
        source_object_key=source_object_key,
        metadata=project_submission_metadata(submission),
    )
    payload = recipient_list_member_payload(payload_data)
    if payload is None:
        return None
    return RecipientListMemberPayload(
        list_key=list_key,
        source_object_key=source_object_key,
        payload=payload,
    )

def recipient_list_send_member_payload(
    source_object_key: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    member = payload["member"]
    return {
        "source_object_key": source_object_key,
        "email": member["email"],
        "status": member["status"],
        "metadata": member["metadata"],
    }
