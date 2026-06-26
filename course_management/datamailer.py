import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import requests
from django.conf import settings
from django.urls import reverse

from course_management import email_templates
from course_management.deadlines import format_deadline_for_email

logger = logging.getLogger(__name__)

EMAIL_PREFERENCE_CATEGORIES = {
    "email_submission_confirmations": {
        "tag": "submission-results",
        "label": "Homework and project submissions",
    },
    "email_deadline_reminders": {
        "tag": "deadline-reminders",
        "label": "Deadline reminders",
    },
    "email_course_updates": {
        "tag": "course-updates",
        "label": "General course-related emails",
    },
}


@dataclass(frozen=True)
class DatamailerConfig:
    url: str
    api_key: str
    client: str
    audience: str
    from_email: str = ""
    strict: bool = False

    @classmethod
    def from_settings(cls) -> "DatamailerConfig | None":
        url = getattr(settings, "DATAMAILER_URL", "")
        api_key = getattr(settings, "DATAMAILER_API_KEY", "")
        client = getattr(settings, "DATAMAILER_CLIENT", "")
        audience = getattr(settings, "DATAMAILER_AUDIENCE", "")
        from_email = getattr(settings, "DATAMAILER_FROM_EMAIL", "")

        if not all([url, api_key, client, audience]):
            return None

        strict = getattr(settings, "DATAMAILER_STRICT", False)
        return cls(
            url=url.rstrip("/"),
            api_key=api_key,
            client=client,
            audience=audience,
            from_email=from_email,
            strict=strict,
        )


class DatamailerClient:
    def __init__(
        self,
        config: DatamailerConfig,
        session: requests.Session | None = None,
    ):
        self.config = config
        self.session = session or requests.Session()

    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        url = f"{self.config.url}{path}"
        request_kwargs: dict[str, Any] = {
            "json": json,
            "timeout": 10,
            "headers": {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
        }
        if params is not None:
            request_kwargs["params"] = params

        response = self.session.request(
            method,
            url,
            **request_kwargs,
        )
        response.raise_for_status()

        if not response.content:
            return None

        return response.json()

    def upsert_contact(
        self, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        return self.request("POST", "/api/contacts", json=payload)

    def send_transactional(
        self, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        return self.request(
            "POST",
            "/api/transactional/send",
            json=payload,
        )

    def contact_status(self, email: str) -> dict[str, Any] | None:
        return self.request(
            "GET",
            "/api/contacts/status",
            params={
                "email": email,
                "audience": self.config.audience,
                "client": self.config.client,
            },
        )

    def contact_history(
        self,
        contact_id: int,
        *,
        limit: int = 25,
    ) -> dict[str, Any] | None:
        return self.request(
            "GET",
            f"/api/contacts/{contact_id}/history",
            params={
                "audience": self.config.audience,
                "client": self.config.client,
                "limit": limit,
            },
        )

    def transactional_message_status(
        self,
        message_id: int,
    ) -> dict[str, Any] | None:
        return self.request(
            "GET",
            f"/api/transactional/messages/{message_id}",
        )

    def contact_preferences(
        self,
        email: str,
        *,
        category_tags: list[str],
    ) -> dict[str, Any] | None:
        return self.request(
            "GET",
            "/api/contacts/preferences",
            params={
                "email": email,
                "audience": self.config.audience,
                "client": self.config.client,
                "category_tags": ",".join(category_tags),
            },
        )

    def update_contact_preferences(
        self,
        email: str,
        categories: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        return self.request(
            "PUT",
            "/api/contacts/preferences",
            json={
                "email": email,
                "audience": self.config.audience,
                "client": self.config.client,
                "categories": categories,
            },
        )

    def upsert_recipient_list_member(
        self,
        list_key: str,
        source_object_key: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        return self.request(
            "PUT",
            f"/api/recipient-lists/{list_key}/members/{source_object_key}",
            json=payload,
        )

    def bulk_upsert_recipient_list_members(
        self,
        list_key: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        return self.request(
            "POST",
            f"/api/recipient-lists/{list_key}/members/bulk-upsert",
            json=payload,
        )

    def reconcile_recipient_list_members(
        self,
        list_key: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        return self.request(
            "POST",
            f"/api/recipient-lists/{list_key}/members/reconcile",
            json=payload,
        )

    def send_recipient_list_transactional(
        self,
        list_key: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        return self.request(
            "POST",
            f"/api/recipient-lists/{list_key}/transactional-send",
            json=payload,
        )

    def send_transient_recipient_list_transactional(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        return self.request(
            "POST",
            "/api/transient-recipient-lists/transactional-send",
            json=payload,
        )

    def upsert_campaign(
        self,
        external_key: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        return self.request(
            "PUT",
            f"/api/campaigns/{external_key}",
            json={
                "audience": self.config.audience,
                "client": self.config.client,
            }
            | payload,
        )

    def campaign(
        self,
        external_key: str,
    ) -> dict[str, Any] | None:
        return self.request(
            "GET",
            f"/api/campaigns/{external_key}",
            params={
                "audience": self.config.audience,
                "client": self.config.client,
            },
        )

    def queue_campaign(
        self,
        external_key: str,
    ) -> dict[str, Any] | None:
        return self.request(
            "POST",
            f"/api/campaigns/{external_key}/queue",
            json={
                "audience": self.config.audience,
                "client": self.config.client,
            },
        )

    def cancel_campaign(
        self,
        external_key: str,
    ) -> dict[str, Any] | None:
        return self.request(
            "POST",
            f"/api/campaigns/{external_key}/cancel",
            json={
                "audience": self.config.audience,
                "client": self.config.client,
            },
        )

    def preview_campaign(
        self,
        external_key: str,
    ) -> dict[str, Any] | None:
        return self.request(
            "POST",
            f"/api/campaigns/{external_key}/preview",
            json={
                "audience": self.config.audience,
                "client": self.config.client,
            },
        )

    def test_send_campaign(
        self,
        external_key: str,
        emails: list[str],
    ) -> dict[str, Any] | None:
        return self.request(
            "POST",
            f"/api/campaigns/{external_key}/test-send",
            json={
                "audience": self.config.audience,
                "client": self.config.client,
                "emails": emails,
            },
        )


def datamailer_enabled() -> bool:
    return DatamailerConfig.from_settings() is not None


def course_family_slug(course) -> str:
    slug = course.slug
    return re.sub(r"[-_ ]?\d{4}$", "", slug).strip("-_ ") or slug


def contact_tags_for_course(course) -> list[str]:
    family_slug = course_family_slug(course)
    return [
        f"course-{family_slug}",
        f"course-cohort-{course.slug}",
    ]


def contact_payload_for_user(
    user, course=None
) -> dict[str, Any] | None:
    email = (user.email or "").strip().lower()
    if not email:
        return None

    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    tags = []
    custom_fields = {
        "course_platform_user_id": str(user.pk),
        "username": user.username or "",
    }

    if course is not None:
        tags.extend(contact_tags_for_course(course))
        custom_fields["course_slug"] = course.slug
        custom_fields["course_family_slug"] = course_family_slug(course)
        custom_fields["course_cohort_slug"] = course.slug
        custom_fields["course_title"] = course.title

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


def registration_list_key(registration) -> str:
    if registration.course_id:
        return registration.course.slug
    return registration.campaign.slug


def course_enrolled_list_key(course) -> str:
    return f"{course.slug}:@e"


def homework_submitters_list_key(homework) -> str:
    return f"{homework.course.slug}:@e:@homework:{homework.slug}"


def project_submitters_list_key(project) -> str:
    return f"{project.course.slug}:@e:@project:{project.slug}"


def project_passed_list_key(project) -> str:
    return f"{project_submitters_list_key(project)}:@passed"


def course_graduates_list_key(course) -> str:
    return f"{course.slug}:@e:@graduated"


def public_url(path: str) -> str:
    base_url = getattr(settings, "PUBLIC_BASE_URL", "")
    if not base_url:
        return path
    return urljoin(f"{base_url.rstrip('/')}/", path.lstrip("/"))


def email_preference_category_tags() -> list[str]:
    return [
        category["tag"]
        for category in EMAIL_PREFERENCE_CATEGORIES.values()
    ]


def email_preference_values_from_response(
    response: dict[str, Any] | None,
) -> dict[str, bool]:
    if not response:
        return {}
    by_tag = {
        category.get("tag"): category
        for category in response.get("categories", [])
        if isinstance(category, dict)
    }
    values = {}
    for field, category in EMAIL_PREFERENCE_CATEGORIES.items():
        item = by_tag.get(category["tag"])
        if item is not None and isinstance(item.get("enabled"), bool):
            values[field] = item["enabled"]
    return values


def get_email_preferences_for_user(user) -> dict[str, bool] | None:
    email = (user.email or "").strip().lower()
    if not email:
        return None
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    client = DatamailerClient(config)
    try:
        response = client.contact_preferences(
            email,
            category_tags=email_preference_category_tags(),
        )
    except requests.RequestException:
        logger.exception(
            "Datamailer preference lookup failed for user_id=%s",
            user.pk,
        )
        if config.strict:
            raise
        return None
    return email_preference_values_from_response(response)


def apply_email_preferences_to_user(user) -> bool:
    preferences = get_email_preferences_for_user(user)
    if preferences is None:
        return False
    for field, enabled in preferences.items():
        setattr(user, field, enabled)
    return True


def update_email_preferences_for_user(
    user,
    values: dict[str, bool],
) -> bool:
    email = (user.email or "").strip().lower()
    if not email:
        return False
    config = DatamailerConfig.from_settings()
    if config is None:
        return False

    categories = []
    for field, enabled in values.items():
        category = EMAIL_PREFERENCE_CATEGORIES.get(field)
        if category is None:
            continue
        categories.append(
            {
                "tag": category["tag"],
                "label": category["label"],
                "enabled": bool(enabled),
            }
        )
    if not categories:
        return False

    client = DatamailerClient(config)
    try:
        client.update_contact_preferences(email, categories)
    except requests.RequestException:
        logger.exception(
            "Datamailer preference update failed for user_id=%s",
            user.pk,
        )
        if config.strict:
            raise
        return False
    return True


def registration_contact_payload(registration) -> dict[str, Any] | None:
    email = (
        (registration.email_normalized or registration.email or "")
        .strip()
        .lower()
    )
    if not email:
        return None

    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    tags = []
    course = registration.course
    if course is not None:
        tags = contact_tags_for_course(course)

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
    }


def recipient_list_member_payload(
    *,
    list_type: str,
    list_name: str,
    email: str,
    source_object_key: str,
    metadata: dict[str, Any],
) -> dict[str, Any] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    return {
        "audience": config.audience,
        "client": config.client,
        "list": {
            "type": list_type,
            "name": list_name,
            "metadata": metadata,
        },
        "member": {
            "email": email.strip().lower(),
            "status": "active",
            "metadata": metadata
            | {"source_object_key": source_object_key},
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
) -> tuple[str, str, dict[str, Any]] | None:
    email = (
        (registration.email_normalized or registration.email or "")
        .strip()
        .lower()
    )
    if not email:
        return None

    course = registration.course
    list_key = registration_list_key(registration)
    list_name = (
        f"{course.title} registrants"
        if course is not None
        else f"{registration.campaign.title} registrants"
    )
    source_object_key = f"registration:{registration.pk}"
    metadata = {
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
    payload = recipient_list_member_payload(
        list_type="registrants",
        list_name=list_name,
        email=email,
        source_object_key=source_object_key,
        metadata=metadata,
    )
    if payload is None:
        return None
    return list_key, source_object_key, payload


def enrollment_recipient_list_payload(
    enrollment,
) -> tuple[str, str, dict[str, Any]] | None:
    email = (enrollment.student.email or "").strip().lower()
    if not email:
        return None

    course = enrollment.course
    list_key = course_enrolled_list_key(course)
    source_object_key = f"user:{enrollment.student_id}"
    metadata = {
        "enrollment_id": enrollment.pk,
        "user_id": enrollment.student_id,
        "course_slug": course.slug,
        "display_name": enrollment.display_name,
    }
    payload = recipient_list_member_payload(
        list_type="custom",
        list_name=f"{course.title} enrolled learners",
        email=email,
        source_object_key=source_object_key,
        metadata=metadata,
    )
    if payload is None:
        return None
    return list_key, source_object_key, payload


def homework_submission_recipient_list_payload(
    submission,
) -> tuple[str, str, dict[str, Any]] | None:
    email = (submission.student.email or "").strip().lower()
    if not email:
        return None

    homework = submission.homework
    course = homework.course
    list_key = homework_submitters_list_key(homework)
    source_object_key = f"homework-submission:{submission.pk}"
    metadata = {
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
        "homework_url": public_url(
            reverse(
                "homework",
                kwargs={
                    "course_slug": course.slug,
                    "homework_slug": homework.slug,
                },
            )
        ),
    }
    payload = recipient_list_member_payload(
        list_type="homework_submitters",
        list_name=f"{course.title} {homework.title} submitters",
        email=email,
        source_object_key=source_object_key,
        metadata=metadata,
    )
    if payload is None:
        return None
    return list_key, source_object_key, payload


def project_submission_recipient_list_payload(
    submission,
) -> tuple[str, str, dict[str, Any]] | None:
    email = (submission.student.email or "").strip().lower()
    if not email:
        return None

    project = submission.project
    course = project.course
    list_key = project_submitters_list_key(project)
    source_object_key = f"project-submission:{submission.pk}"
    metadata = {
        "submission_id": submission.pk,
        "user_id": submission.student_id,
        "course_slug": course.slug,
        "project_slug": project.slug,
        "submitted_at": submission.submitted_at.isoformat()
        if submission.submitted_at
        else "",
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
        "github_link": submission.github_link,
        "commit_id": submission.commit_id,
        "faq_contribution_url": submission.faq_contribution_url or "",
        "project_url": public_url(
            reverse(
                "project",
                kwargs={
                    "course_slug": course.slug,
                    "project_slug": project.slug,
                },
            )
        ),
        "reviewed_enough_peers": submission.reviewed_enough_peers,
        "passed": submission.passed,
    }
    payload = recipient_list_member_payload(
        list_type="project_submitters",
        list_name=f"{course.title} {project.title} submitters",
        email=email,
        source_object_key=source_object_key,
        metadata=metadata,
    )
    if payload is None:
        return None
    return list_key, source_object_key, payload


def sync_contact(user, course=None) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    payload = contact_payload_for_user(user, course=course)
    if payload is None:
        return

    client = DatamailerClient(config)
    if config.from_email and "from_email" not in payload:
        payload = payload | {"from_email": config.from_email}

    try:
        client.upsert_contact(payload)
    except requests.RequestException:
        logger.exception(
            "Datamailer contact sync failed for user_id=%s",
            user.pk,
        )
        if config.strict:
            raise


def _sync_contact_and_membership(
    config, contact_payload, list_payload, *, label, id_field, obj
):
    """Upsert a contact and its recipient-list membership in one call.

    No-op if either payload is None. On request failure, logs with the
    given ``label``/``id_field`` context and re-raises when config.strict.
    """
    if contact_payload is None or list_payload is None:
        return

    client = DatamailerClient(config)
    try:
        client.upsert_contact(contact_payload)
        list_key, source_object_key, payload = list_payload
        client.upsert_recipient_list_member(
            list_key, source_object_key, payload
        )
    except requests.RequestException:
        logger.exception(
            "Datamailer %s sync failed for %s=%s",
            label,
            id_field,
            obj.pk,
        )
        if config.strict:
            raise


def sync_registration_to_datamailer(registration) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    _sync_contact_and_membership(
        config,
        registration_contact_payload(registration),
        registration_recipient_list_payload(registration),
        label="registration",
        id_field="registration_id",
        obj=registration,
    )


def sync_enrollment_to_datamailer(enrollment) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    _sync_contact_and_membership(
        config,
        contact_payload_for_user(
            enrollment.student, course=enrollment.course
        ),
        enrollment_recipient_list_payload(enrollment),
        label="enrollment",
        id_field="enrollment_id",
        obj=enrollment,
    )


def sync_homework_submission_to_datamailer(submission) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    _sync_contact_and_membership(
        config,
        contact_payload_for_user(
            submission.student, course=submission.homework.course
        ),
        homework_submission_recipient_list_payload(submission),
        label="homework submission",
        id_field="submission_id",
        obj=submission,
    )


def sync_project_submission_to_datamailer(submission) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    _sync_contact_and_membership(
        config,
        contact_payload_for_user(
            submission.student, course=submission.project.course
        ),
        project_submission_recipient_list_payload(submission),
        label="project submission",
        id_field="submission_id",
        obj=submission,
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


def homework_score_notification_members(
    homework,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    list_data = {
        "type": "homework_submitters",
        "name": f"{homework.course.title} {homework.title} submitters",
        "metadata": {
            "course_slug": homework.course.slug,
            "homework_slug": homework.slug,
        },
    }
    members = []
    submissions = homework.submission_set.select_related(
        "student", "homework__course"
    ).order_by("student_id", "-submitted_at", "-id")
    seen_students = set()
    for submission in submissions:
        if not getattr(submission.student, "email_submission_confirmations", True):
            continue
        if submission.student_id in seen_students:
            continue
        item = homework_submission_recipient_list_payload(submission)
        if item is None:
            continue
        seen_students.add(submission.student_id)
        _, source_object_key, member_payload = item
        list_data = member_payload["list"]
        members.append(
            recipient_list_send_member_payload(
                source_object_key, member_payload
            )
        )
    return list_data, members


def project_score_notification_members(
    project,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    list_data = {
        "type": "project_submitters",
        "name": f"{project.course.title} {project.title} submitters",
        "metadata": {
            "course_slug": project.course.slug,
            "project_slug": project.slug,
        },
    }
    members = []
    submissions = project.projectsubmission_set.select_related(
        "student", "project__course"
    ).order_by("student_id", "-submitted_at", "-id")
    seen_students = set()
    for submission in submissions:
        if not getattr(submission.student, "email_submission_confirmations", True):
            continue
        if submission.student_id in seen_students:
            continue
        item = project_submission_recipient_list_payload(submission)
        if item is None:
            continue
        seen_students.add(submission.student_id)
        _, source_object_key, member_payload = item
        list_data = member_payload["list"]
        members.append(
            recipient_list_send_member_payload(
                source_object_key, member_payload
            )
        )
    return list_data, members


def project_passed_recipient_list_payload(
    project,
) -> tuple[str, dict[str, Any]] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    course = project.course
    list_key = project_passed_list_key(project)
    list_data = {
        "type": "custom",
        "name": f"{course.title} {project.title} passed learners",
        "metadata": {
            "course_slug": course.slug,
            "project_slug": project.slug,
            "project_id": project.pk,
            "outcome": "project_passed",
        },
    }
    members = []
    submissions = project.projectsubmission_set.select_related(
        "student", "project__course"
    ).order_by("student_id", "-submitted_at", "-id")
    seen_students = set()
    for submission in submissions:
        if submission.student_id in seen_students:
            continue
        seen_students.add(submission.student_id)
        if not submission.passed:
            continue
        item = project_submission_recipient_list_payload(submission)
        if item is None:
            continue
        _, source_object_key, member_payload = item
        member = recipient_list_send_member_payload(
            source_object_key, member_payload
        )
        member["metadata"] = member["metadata"] | {
            "outcome": "project_passed",
        }
        members.append(member)

    payload = {
        "audience": config.audience,
        "client": config.client,
        "list": list_data,
        "members": members,
    }
    return list_key, payload


def project_passed_recipient_list_member_payload(
    submission,
) -> tuple[str, str, dict[str, Any]] | None:
    item = project_submission_recipient_list_payload(submission)
    if item is None:
        return None

    project = submission.project
    course = project.course
    _, source_object_key, payload = item
    return project_passed_list_key(project), source_object_key, {
        **payload,
        "list": {
            "type": "custom",
            "name": f"{course.title} {project.title} passed learners",
            "metadata": {
                "course_slug": course.slug,
                "project_slug": project.slug,
                "project_id": project.pk,
                "outcome": "project_passed",
            },
        },
        "member": {
            **payload["member"],
            "metadata": payload["member"]["metadata"]
            | {
                "outcome": "project_passed",
            },
        },
    }


def homework_score_notification_payload(
    homework,
) -> tuple[str, dict[str, Any]] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None


    course = homework.course
    list_key = homework_submitters_list_key(homework)
    list_data, members = homework_score_notification_members(homework)
    course_url = public_url(
        reverse("course", kwargs={"course_slug": course.slug})
    )
    homework_url = public_url(
        reverse(
            "homework",
            kwargs={
                "course_slug": course.slug,
                "homework_slug": homework.slug,
            },
        )
    )
    leaderboard_url = public_url(
        reverse("leaderboard", kwargs={"course_slug": course.slug})
    )
    profile_url = public_url(reverse("account_settings"))

    payload = {
        "audience": config.audience,
        "client": config.client,
        "template_key": email_templates.HOMEWORK_SCORE_NOTIFICATION,
        "category_tag": "submission-results",
        "idempotency_key": f"homework-score:{course.slug}:{homework.slug}",
        "context": {
            "course_slug": course.slug,
            "course_title": course.title,
            "homework_slug": homework.slug,
            "homework_title": homework.title,
            "course_url": course_url,
            "homework_url": homework_url,
            "scores_url": homework_url,
            "leaderboard_url": leaderboard_url,
            "profile_url": profile_url,
            "notification_footer": (
                f"You are receiving this because you submitted {homework.title} "
                f"for {course.title} and homework/project submission emails "
                "are enabled in your profile."
            ),
            "notification_footer_text": (
                "If you don't want to receive homework/project submission "
                "and score emails, turn off homework and project submission "
                f"emails in your profile: {profile_url}"
            ),
        },
        "list": list_data,
        "members": members,
        "metadata": {
            "source": "course-management-platform",
            "event": "homework_score_publication",
            "course_slug": course.slug,
            "homework_slug": homework.slug,
            "homework_id": homework.pk,
            "preference_key": "email_submission_confirmations",
            "cmp_preference_key": "email_submission_confirmations",
        },
    }
    if config.from_email:
        payload["from_email"] = config.from_email
    return list_key, payload


def project_score_notification_payload(
    project,
) -> tuple[str, dict[str, Any]] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None


    course = project.course
    list_key = project_submitters_list_key(project)
    list_data, members = project_score_notification_members(project)
    project_url = public_url(
        reverse(
            "project",
            kwargs={
                "course_slug": course.slug,
                "project_slug": project.slug,
            },
        )
    )
    project_results_url = public_url(
        reverse(
            "project_results",
            kwargs={
                "course_slug": course.slug,
                "project_slug": project.slug,
            },
        )
    )
    course_url = public_url(
        reverse("course", kwargs={"course_slug": course.slug})
    )
    leaderboard_url = public_url(
        reverse("leaderboard", kwargs={"course_slug": course.slug})
    )
    profile_url = public_url(reverse("account_settings"))

    payload = {
        "audience": config.audience,
        "client": config.client,
        "template_key": email_templates.PROJECT_SCORE_NOTIFICATION,
        "category_tag": "submission-results",
        "idempotency_key": f"project-score:{course.slug}:{project.slug}",
        "context": {
            "course_slug": course.slug,
            "course_title": course.title,
            "project_slug": project.slug,
            "project_title": project.title,
            "course_url": course_url,
            "project_url": project_url,
            "project_results_url": project_results_url,
            "scores_url": project_results_url,
            "leaderboard_url": leaderboard_url,
            "profile_url": profile_url,
            "notification_footer": (
                f"You are receiving this because you submitted {project.title} "
                f"for {course.title} and homework/project submission emails "
                "are enabled in your profile."
            ),
            "notification_footer_text": (
                "If you don't want to receive homework/project submission "
                "and score emails, turn off homework and project submission "
                f"emails in your profile: {profile_url}"
            ),
        },
        "list": list_data,
        "members": members,
        "metadata": {
            "source": "course-management-platform",
            "event": "project_score_publication",
            "course_slug": course.slug,
            "project_slug": project.slug,
            "project_id": project.pk,
            "preference_key": "email_submission_confirmations",
            "cmp_preference_key": "email_submission_confirmations",
        },
    }
    if config.from_email:
        payload["from_email"] = config.from_email
    return list_key, payload


def _assigned_review_links(submission) -> list[dict[str, Any]]:
    """The non-optional peer reviews this submission's author must complete,
    each with a direct evaluation link and the target's GitHub link."""
    project = submission.project
    course = project.course
    reviews = (
        submission.reviewers.filter(optional=False)
        .select_related("submission_under_evaluation")
        .order_by("id")
    )
    items = []
    for review in reviews:
        target = review.submission_under_evaluation
        items.append(
            {
                "review_id": review.id,
                "eval_url": public_url(
                    reverse(
                        "projects_eval_submit",
                        kwargs={
                            "course_slug": course.slug,
                            "project_slug": project.slug,
                            "review_id": review.id,
                        },
                    )
                ),
                "submission_github_link": (
                    getattr(target, "github_link", "") or ""
                ),
            }
        )
    return items


def peer_review_assignment_recipient_list_payload(
    submission,
) -> tuple[str, str, dict[str, Any]] | None:
    email = (submission.student.email or "").strip().lower()
    if not email:
        return None

    project = submission.project
    course = project.course
    list_key = project_submitters_list_key(project)
    source_object_key = f"project-submission:{submission.pk}"
    assigned_reviews = _assigned_review_links(submission)
    deadline = format_deadline_for_email(
        project.peer_review_due_date,
        submission.student,
    )
    metadata = {
        "submission_id": submission.pk,
        "user_id": submission.student_id,
        "course_slug": course.slug,
        "project_slug": project.slug,
        "submitted_at": submission.submitted_at.isoformat()
        if submission.submitted_at
        else "",
        "github_link": submission.github_link,
        "evaluations_url": public_url(
            reverse(
                "projects_eval",
                kwargs={
                    "course_slug": course.slug,
                    "project_slug": project.slug,
                },
            )
        ),
        "number_of_peers_to_evaluate": project.number_of_peers_to_evaluate,
        "assigned_reviews": assigned_reviews,
        "assigned_reviews_count": len(assigned_reviews),
        "deadline_weekday": deadline["deadline_weekday"],
        "deadline_date": deadline["deadline_date"],
        "deadline_time": deadline["deadline_time"],
        "deadline_timezone": deadline["deadline_timezone"],
        "deadline_summary": deadline["deadline_summary"],
    }
    payload = recipient_list_member_payload(
        list_type="project_submitters",
        list_name=f"{course.title} {project.title} submitters",
        email=email,
        source_object_key=source_object_key,
        metadata=metadata,
    )
    if payload is None:
        return None
    return list_key, source_object_key, payload


def peer_review_assignment_notification_members(
    project,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    list_data = {
        "type": "project_submitters",
        "name": f"{project.course.title} {project.title} submitters",
        "metadata": {
            "course_slug": project.course.slug,
            "project_slug": project.slug,
        },
    }
    members = []
    submissions = project.projectsubmission_set.select_related(
        "student", "project__course"
    ).order_by("student_id", "-submitted_at", "-id")
    seen_students = set()
    for submission in submissions:
        if not getattr(submission.student, "email_submission_confirmations", True):
            continue
        if submission.student_id in seen_students:
            continue
        item = peer_review_assignment_recipient_list_payload(submission)
        if item is None:
            continue
        seen_students.add(submission.student_id)
        _, source_object_key, member_payload = item
        list_data = member_payload["list"]
        members.append(
            recipient_list_send_member_payload(
                source_object_key, member_payload
            )
        )
    return list_data, members


def peer_review_assignment_notification_payload(
    project,
) -> tuple[str, dict[str, Any]] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    course = project.course
    list_key = project_submitters_list_key(project)
    list_data, members = peer_review_assignment_notification_members(project)
    course_url = public_url(
        reverse("course", kwargs={"course_slug": course.slug})
    )
    project_url = public_url(
        reverse(
            "project",
            kwargs={
                "course_slug": course.slug,
                "project_slug": project.slug,
            },
        )
    )
    evaluations_url = public_url(
        reverse(
            "projects_eval",
            kwargs={
                "course_slug": course.slug,
                "project_slug": project.slug,
            },
        )
    )
    leaderboard_url = public_url(
        reverse("leaderboard", kwargs={"course_slug": course.slug})
    )
    profile_url = public_url(reverse("account_settings"))
    deadline = format_deadline_for_email(project.peer_review_due_date)
    num_peers = project.number_of_peers_to_evaluate

    payload = {
        "audience": config.audience,
        "client": config.client,
        "template_key": email_templates.PEER_REVIEW_ASSIGNMENT,
        "category_tag": "submission-results",
        "idempotency_key": (
            f"peer-review-assignment:{course.slug}:{project.slug}"
        ),
        "context": {
            "course_slug": course.slug,
            "course_title": course.title,
            "project_slug": project.slug,
            "project_title": project.title,
            "course_url": course_url,
            "project_url": project_url,
            "evaluations_url": evaluations_url,
            "leaderboard_url": leaderboard_url,
            "profile_url": profile_url,
            "number_of_peers_to_evaluate": num_peers,
            "peer_review_due_at": project.peer_review_due_date.isoformat(),
            "deadline_weekday": deadline["deadline_weekday"],
            "deadline_date": deadline["deadline_date"],
            "deadline_time": deadline["deadline_time"],
            "deadline_summary": deadline["deadline_summary"],
            "email_subject": f"Peer review is open: {project.title}",
            "email_preview": (
                f"Time to evaluate {num_peers} projects for "
                f"{project.title}."
            ),
            "intro_text": (
                f"Thanks for submitting {project.title} in {course.title}. "
                f"Peer review is now open - you have {num_peers} projects to "
                "evaluate before the deadline."
            ),
            "notification_footer": (
                f"You are receiving this because you submitted {project.title} "
                f"for {course.title} and homework/project submission emails "
                "are enabled in your profile."
            ),
            "notification_footer_text": (
                "If you don't want to receive homework/project submission "
                "and score emails, turn off homework and project submission "
                f"emails in your profile: {profile_url}"
            ),
        },
        "list": list_data,
        "members": members,
        "metadata": {
            "source": "course-management-platform",
            "event": "peer_review_assignment",
            "course_slug": course.slug,
            "project_slug": project.slug,
            "project_id": project.pk,
            "preference_key": "email_submission_confirmations",
            "cmp_preference_key": "email_submission_confirmations",
        },
    }
    if config.from_email:
        payload["from_email"] = config.from_email
    return list_key, payload


def certificate_availability_notification_payload(
    enrollment,
) -> dict[str, Any] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    email = (enrollment.student.email or "").strip().lower()
    certificate_url = (enrollment.certificate_url or "").strip()
    if not email or not certificate_url:
        return None
    if not getattr(enrollment.student, "email_course_updates", True):
        return None


    course = enrollment.course
    course_url = public_url(
        reverse("course", kwargs={"course_slug": course.slug})
    )
    certificate_url = public_url(certificate_url)
    profile_url = public_url(reverse("account_settings"))

    payload = {
        "audience": config.audience,
        "client": config.client,
        "email": email,
        "template_key": (
            email_templates.CERTIFICATE_AVAILABILITY_NOTIFICATION
        ),
        "category_tag": "course-updates",
        "idempotency_key": f"certificate-available:{enrollment.pk}",
        "context": {
            "course_slug": course.slug,
            "course_title": course.title,
            "certificate_url": certificate_url,
            "course_url": course_url,
            "profile_url": profile_url,
            "email_subject": f"Certificate available: {course.title}",
            "email_preview": (
                "Your course certificate is available to download."
            ),
            "intro_text": (
                f"Congratulations - your certificate for {course.title} "
                "is available."
            ),
            "download_text": (
                f"You can download your certificate here: "
                f"{certificate_url}"
            ),
            "notification_category": "course-related emails",
            "notification_footer": (
                "You are receiving this because general course-related "
                "emails are enabled."
            ),
        },
        "metadata": {
            "source": "course-management-platform",
            "event": "certificate_availability",
            "preference_key": "email_course_updates",
            "cmp_preference_key": "email_course_updates",
            "course_slug": course.slug,
            "enrollment_id": enrollment.pk,
            "user_id": enrollment.student_id,
        },
    }
    if config.from_email:
        payload["from_email"] = config.from_email
    return payload


def course_graduate_recipient_list_payload(
    enrollment,
) -> tuple[str, dict[str, Any]] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    email = (enrollment.student.email or "").strip().lower()
    certificate_url = (enrollment.certificate_url or "").strip()
    if not email or not certificate_url:
        return None

    course = enrollment.course
    list_key = course_graduates_list_key(course)
    source_object_key = f"enrollment:{enrollment.pk}"
    metadata = {
        "enrollment_id": enrollment.pk,
        "user_id": enrollment.student_id,
        "course_slug": course.slug,
        "display_name": enrollment.display_name,
        "total_score": enrollment.total_score,
        "certificate_url": public_url(certificate_url),
        "outcome": "course_graduated",
    }
    member_payload = recipient_list_member_payload(
        list_type="custom",
        list_name=f"{course.title} graduates",
        email=email,
        source_object_key=source_object_key,
        metadata=metadata,
    )
    if member_payload is None:
        return None

    return list_key, {
        "audience": config.audience,
        "client": config.client,
        "list": member_payload["list"],
        "members": [
            recipient_list_send_member_payload(
                source_object_key, member_payload
            )
        ],
    }


def course_graduate_recipient_list_member_payload(
    enrollment,
) -> tuple[str, str, dict[str, Any]] | None:
    list_payload = course_graduate_recipient_list_payload(enrollment)
    if list_payload is None:
        return None

    list_key, payload = list_payload
    member = payload["members"][0]
    return list_key, member["source_object_key"], {
        "audience": payload["audience"],
        "client": payload["client"],
        "list": payload["list"],
        "member": {
            "email": member["email"],
            "status": member["status"],
            "metadata": member["metadata"],
        },
    }


def recipient_list_member_sync_payload(
    config: DatamailerConfig,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "audience": config.audience,
        "client": config.client,
        "list": payload["list"],
        "members": payload["members"],
    }


def _remove_recipient_list_memberships(
    config,
    list_payloads,
    *,
    label,
    id_field,
    obj,
) -> None:
    client = DatamailerClient(config)
    try:
        for list_payload in list_payloads:
            if list_payload is None:
                continue
            list_key, source_object_key, payload = list_payload
            client.upsert_recipient_list_member(
                list_key,
                source_object_key,
                removed_recipient_list_member_payload(payload),
            )
    except requests.RequestException:
        logger.exception(
            "Datamailer %s removal failed for %s=%s",
            label,
            id_field,
            obj.pk,
        )
        if config.strict:
            raise


def remove_registration_from_datamailer(registration) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    _remove_recipient_list_memberships(
        config,
        [registration_recipient_list_payload(registration)],
        label="registration",
        id_field="registration_id",
        obj=registration,
    )


def remove_enrollment_from_datamailer(enrollment) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    _remove_recipient_list_memberships(
        config,
        [
            enrollment_recipient_list_payload(enrollment),
            course_graduate_recipient_list_member_payload(enrollment),
        ],
        label="enrollment",
        id_field="enrollment_id",
        obj=enrollment,
    )


def remove_homework_submission_from_datamailer(submission) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    _remove_recipient_list_memberships(
        config,
        [homework_submission_recipient_list_payload(submission)],
        label="homework submission",
        id_field="submission_id",
        obj=submission,
    )


def remove_project_submission_from_datamailer(submission) -> None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return

    list_payloads = [project_submission_recipient_list_payload(submission)]
    if submission.passed:
        list_payloads.append(
            project_passed_recipient_list_member_payload(submission)
        )
    _remove_recipient_list_memberships(
        config,
        list_payloads,
        label="project submission",
        id_field="submission_id",
        obj=submission,
    )


def recipient_list_send_payload(
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if key
        not in {
            "list",
            "members",
            "member_sync",
            "remove_absent_members",
        }
    }


def send_homework_score_notification(homework) -> dict[str, Any] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    list_payload = homework_score_notification_payload(homework)
    if list_payload is None:
        return None

    client = DatamailerClient(config)
    try:
        list_key, payload = list_payload
        client.bulk_upsert_recipient_list_members(
            list_key,
            recipient_list_member_sync_payload(config, payload),
        )
        return client.send_recipient_list_transactional(
            list_key, recipient_list_send_payload(payload)
        )
    except requests.RequestException:
        logger.exception(
            "Datamailer homework score notification failed for homework_id=%s",
            homework.pk,
        )
        if config.strict:
            raise
        return None


def send_project_score_notification(project) -> dict[str, Any] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    list_payload = project_score_notification_payload(project)
    if list_payload is None:
        return None

    client = DatamailerClient(config)
    try:
        list_key, payload = list_payload
        passed_list_payload = project_passed_recipient_list_payload(project)
        client.bulk_upsert_recipient_list_members(
            list_key,
            recipient_list_member_sync_payload(config, payload),
        )
        if passed_list_payload is not None:
            passed_list_key, passed_payload = passed_list_payload
            client.reconcile_recipient_list_members(
                passed_list_key,
                recipient_list_member_sync_payload(config, passed_payload),
            )
        return client.send_recipient_list_transactional(
            list_key, recipient_list_send_payload(payload)
        )
    except requests.RequestException:
        logger.exception(
            "Datamailer project score notification failed for project_id=%s",
            project.pk,
        )
        if config.strict:
            raise
        return None


def send_peer_review_assignment_notification(
    project,
) -> dict[str, Any] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    list_payload = peer_review_assignment_notification_payload(project)
    if list_payload is None:
        return None

    client = DatamailerClient(config)
    try:
        list_key, payload = list_payload
        client.bulk_upsert_recipient_list_members(
            list_key,
            recipient_list_member_sync_payload(config, payload),
        )
        return client.send_recipient_list_transactional(
            list_key,
            recipient_list_send_payload(payload),
        )
    except requests.RequestException:
        logger.exception(
            "Datamailer peer review assignment notification failed "
            "for project_id=%s",
            project.pk,
        )
        if config.strict:
            raise
        return None


def send_certificate_availability_notification(
    enrollment,
) -> dict[str, Any] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    graduate_list_payload = course_graduate_recipient_list_payload(enrollment)
    payload = certificate_availability_notification_payload(enrollment)
    if graduate_list_payload is None and payload is None:
        return None

    client = DatamailerClient(config)
    try:
        if graduate_list_payload is not None:
            list_key, list_payload = graduate_list_payload
            client.bulk_upsert_recipient_list_members(
                list_key,
                recipient_list_member_sync_payload(config, list_payload),
            )
        if payload is None:
            return None
        return client.send_transactional(payload)
    except requests.RequestException:
        logger.exception(
            "Datamailer certificate availability notification failed "
            "for enrollment_id=%s",
            enrollment.pk,
        )
        if config.strict:
            raise
        return None


def send_transactional_email(
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    client = DatamailerClient(config)
    if "audience" not in payload:
        payload = payload | {"audience": config.audience}
    if "client" not in payload:
        payload = payload | {"client": config.client}
    if config.from_email and "from_email" not in payload:
        payload = payload | {"from_email": config.from_email}

    try:
        return client.send_transactional(payload)
    except requests.RequestException:
        logger.exception("Datamailer transactional email failed")
        if config.strict:
            raise
        return None


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
