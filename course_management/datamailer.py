import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import requests
from django.conf import settings
from django.urls import reverse

from course_management import email_templates

logger = logging.getLogger(__name__)


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
        return f"course-registrants:{registration.course.slug}"
    return f"course-registrants:{registration.campaign.slug}"


def course_enrolled_list_key(course) -> str:
    return f"course-enrolled:{course.slug}"


def homework_submitters_list_key(homework) -> str:
    return f"homework-submitters:{homework.course.slug}:{homework.slug}"


def project_submitters_list_key(project) -> str:
    return f"project-submitters:{project.course.slug}:{project.slug}"


def public_url(path: str) -> str:
    base_url = getattr(settings, "PUBLIC_BASE_URL", "")
    if not base_url:
        return path
    return urljoin(f"{base_url.rstrip('/')}/", path.lstrip("/"))


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
    ).order_by("id")
    for submission in submissions:
        if not getattr(submission.student, "email_submission_confirmations", True):
            continue
        item = project_submission_recipient_list_payload(submission)
        if item is None:
            continue
        _, source_object_key, member_payload = item
        list_data = member_payload["list"]
        members.append(
            recipient_list_send_member_payload(
                source_object_key, member_payload
            )
        )
    return list_data, members


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
        "member_sync": "reconcile",
        "remove_absent_members": True,
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
        "member_sync": "reconcile",
        "remove_absent_members": True,
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
        "email": email,
        "template_key": (
            email_templates.CERTIFICATE_AVAILABILITY_NOTIFICATION
        ),
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
        return client.send_recipient_list_transactional(
            list_key, payload
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
        return client.send_recipient_list_transactional(
            list_key, payload
        )
    except requests.RequestException:
        logger.exception(
            "Datamailer project score notification failed for project_id=%s",
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

    payload = certificate_availability_notification_payload(enrollment)
    if payload is None:
        return None

    client = DatamailerClient(config)
    try:
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
