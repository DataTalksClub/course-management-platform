from typing import Any

from django.urls import reverse

from course_management import email_templates
from course_management.deadlines import format_deadline_for_email
from courses.registration import render_markdown
from data.models import DatamailerSendAuditType

from .client import DatamailerConfig, public_url
from .keys import (
    contact_tags_for_course,
    course_enrolled_list_key,
    course_family_slug,
    course_graduates_list_key,
    homework_submitters_list_key,
    project_passed_list_key,
    project_submitters_list_key,
    registration_list_key,
)
from .preferences import EMAIL_PREFERENCE_CATEGORIES


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

def registration_campaign_datamailer_payload(campaign) -> dict[str, Any]:
    public_path = reverse(
        "registration_campaign",
        kwargs={"campaign_slug": campaign.slug},
    )
    body_text = (
        campaign.marketing_markdown.strip()
        or campaign.meta_description.strip()
        or campaign.title
    )
    payload: dict[str, Any] = {
        "subject": campaign.title,
        "preview_text": campaign.meta_description[:255],
        "html_body": render_markdown(body_text),
        "text_body": body_text,
        "category_tag": EMAIL_PREFERENCE_CATEGORIES[
            "email_course_updates"
        ]["tag"],
        "include_tags": [],
        "exclude_tags": [],
        "metadata": {
            "cmp_registration_campaign_slug": campaign.slug,
            "registration_url": public_url(public_path),
        },
    }
    if campaign.current_course_id:
        payload["recipient_list_key"] = campaign.current_course.slug
        payload["metadata"] |= {
            "course_slug": campaign.current_course.slug,
            "course_title": campaign.current_course.title,
        }
    return payload


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
        course_url = public_url(
            reverse("course", kwargs={"course_slug": course.slug})
        )
    return {
        "registration_url": public_url(registration_path),
        "course_url": course_url,
        "profile_url": public_url(reverse("account_settings")),
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

    return {
        "audience": config.audience,
        "client": config.client,
        "email": email,
        "template_key": email_templates.REGISTRATION_CONFIRMATION,
        "category_tag": EMAIL_PREFERENCE_CATEGORIES[
            "email_course_updates"
        ]["tag"],
        "idempotency_key": f"registration-confirmation:{registration.pk}",
        "context": _registration_confirmation_context(
            registration,
            campaign,
            course,
            urls,
        ),
        "metadata": _registration_confirmation_metadata(
            registration,
            campaign,
            course,
        ),
    }

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


def _score_notification_urls(course, assignment, route_name, slug_kwarg):
    assignment_url = public_url(
        reverse(
            route_name,
            kwargs={
                "course_slug": course.slug,
                slug_kwarg: assignment.slug,
            },
        )
    )
    return {
        "course_url": public_url(
            reverse("course", kwargs={"course_slug": course.slug})
        ),
        "assignment_url": assignment_url,
        "leaderboard_url": public_url(
            reverse("leaderboard", kwargs={"course_slug": course.slug})
        ),
        "profile_url": public_url(reverse("account_settings")),
    }


def _score_notification_footer(course, assignment, profile_url):
    return {
        "notification_footer": (
            f"You are receiving this because you submitted {assignment.title} "
            f"for {course.title} and homework/project submission emails "
            "are enabled in your profile."
        ),
        "notification_footer_text": (
            "If you don't want to receive homework/project submission "
            "and score emails, turn off homework and project submission "
            f"emails in your profile: {profile_url}"
        ),
    }


def _homework_score_notification_context(homework):
    course = homework.course
    urls = _score_notification_urls(
        course,
        homework,
        "homework",
        "homework_slug",
    )
    homework_url = urls["assignment_url"]
    return {
        "course_slug": course.slug,
        "course_title": course.title,
        "homework_slug": homework.slug,
        "homework_title": homework.title,
        "course_url": urls["course_url"],
        "homework_url": homework_url,
        "scores_url": homework_url,
        "leaderboard_url": urls["leaderboard_url"],
        "profile_url": urls["profile_url"],
        **_score_notification_footer(course, homework, urls["profile_url"]),
    }


def _project_score_notification_context(project):
    course = project.course
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
    profile_url = public_url(reverse("account_settings"))
    return {
        "course_slug": course.slug,
        "course_title": course.title,
        "project_slug": project.slug,
        "project_title": project.title,
        "course_url": public_url(
            reverse("course", kwargs={"course_slug": course.slug})
        ),
        "project_url": project_url,
        "project_results_url": project_results_url,
        "scores_url": project_results_url,
        "leaderboard_url": public_url(
            reverse("leaderboard", kwargs={"course_slug": course.slug})
        ),
        "profile_url": profile_url,
        **_score_notification_footer(course, project, profile_url),
    }


def _homework_score_notification_metadata(homework):
    return {
        "source": "course-management-platform",
        "event": "homework_score_publication",
        "course_slug": homework.course.slug,
        "homework_slug": homework.slug,
        "homework_id": homework.pk,
        "preference_key": "email_submission_confirmations",
        "cmp_preference_key": "email_submission_confirmations",
    }


def _project_score_notification_metadata(project):
    return {
        "source": "course-management-platform",
        "event": "project_score_publication",
        "course_slug": project.course.slug,
        "project_slug": project.slug,
        "project_id": project.pk,
        "preference_key": "email_submission_confirmations",
        "cmp_preference_key": "email_submission_confirmations",
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
    payload = {
        "audience": config.audience,
        "client": config.client,
        "template_key": email_templates.HOMEWORK_SCORE_NOTIFICATION,
        "category_tag": "submission-results",
        "idempotency_key": f"homework-score:{course.slug}:{homework.slug}",
        "context": _homework_score_notification_context(homework),
        "list": list_data,
        "members": members,
        "metadata": _homework_score_notification_metadata(homework),
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
    payload = {
        "audience": config.audience,
        "client": config.client,
        "template_key": email_templates.PROJECT_SCORE_NOTIFICATION,
        "category_tag": "submission-results",
        "idempotency_key": f"project-score:{course.slug}:{project.slug}",
        "context": _project_score_notification_context(project),
        "list": list_data,
        "members": members,
        "metadata": _project_score_notification_metadata(project),
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


def _peer_review_assignment_urls(course, project) -> dict[str, str]:
    return {
        "course_url": public_url(
            reverse("course", kwargs={"course_slug": course.slug})
        ),
        "project_url": public_url(
            reverse(
                "project",
                kwargs={
                    "course_slug": course.slug,
                    "project_slug": project.slug,
                },
            )
        ),
        "evaluations_url": public_url(
            reverse(
                "projects_eval",
                kwargs={
                    "course_slug": course.slug,
                    "project_slug": project.slug,
                },
            )
        ),
        "leaderboard_url": public_url(
            reverse("leaderboard", kwargs={"course_slug": course.slug})
        ),
        "profile_url": public_url(reverse("account_settings")),
    }


def _peer_review_assignment_context(course, project) -> dict[str, Any]:
    urls = _peer_review_assignment_urls(course, project)
    deadline = format_deadline_for_email(project.peer_review_due_date)
    num_peers = project.number_of_peers_to_evaluate
    return {
        "course_slug": course.slug,
        "course_title": course.title,
        "project_slug": project.slug,
        "project_title": project.title,
        **urls,
        "number_of_peers_to_evaluate": num_peers,
        "peer_review_due_at": project.peer_review_due_date.isoformat(),
        "deadline_weekday": deadline["deadline_weekday"],
        "deadline_date": deadline["deadline_date"],
        "deadline_time": deadline["deadline_time"],
        "deadline_summary": deadline["deadline_summary"],
        "email_subject": f"Peer review is open: {project.title}",
        "email_preview": (
            f"Time to evaluate {num_peers} projects for {project.title}."
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
            f"emails in your profile: {urls['profile_url']}"
        ),
    }


def _peer_review_assignment_metadata(course, project) -> dict[str, Any]:
    return {
        "source": "course-management-platform",
        "event": "peer_review_assignment",
        "course_slug": course.slug,
        "project_slug": project.slug,
        "project_id": project.pk,
        "preference_key": "email_submission_confirmations",
        "cmp_preference_key": "email_submission_confirmations",
    }


def peer_review_assignment_notification_payload(
    project,
) -> tuple[str, dict[str, Any]] | None:
    config = DatamailerConfig.from_settings()
    if config is None:
        return None

    course = project.course
    list_key = project_submitters_list_key(project)
    list_data, members = peer_review_assignment_notification_members(project)

    payload = {
        "audience": config.audience,
        "client": config.client,
        "template_key": email_templates.PEER_REVIEW_ASSIGNMENT,
        "category_tag": "submission-results",
        "idempotency_key": (
            f"peer-review-assignment:{course.slug}:{project.slug}"
        ),
        "context": _peer_review_assignment_context(course, project),
        "list": list_data,
        "members": members,
        "metadata": _peer_review_assignment_metadata(course, project),
    }
    if config.from_email:
        payload["from_email"] = config.from_email
    return list_key, payload


def _certificate_availability_urls(enrollment):
    course = enrollment.course
    certificate_url = public_url(enrollment.certificate_url.strip())
    return {
        "course_url": public_url(
            reverse("course", kwargs={"course_slug": course.slug})
        ),
        "certificate_url": certificate_url,
        "profile_url": public_url(reverse("account_settings")),
    }


def _certificate_availability_context(enrollment, urls):
    course = enrollment.course
    certificate_url = urls["certificate_url"]
    return {
        "course_slug": course.slug,
        "course_title": course.title,
        "certificate_url": certificate_url,
        "course_url": urls["course_url"],
        "profile_url": urls["profile_url"],
        "email_subject": f"Certificate available: {course.title}",
        "email_preview": (
            "Your course certificate is available to download."
        ),
        "intro_text": (
            f"Congratulations - your certificate for {course.title} "
            "is available."
        ),
        "download_text": (
            f"You can download your certificate here: {certificate_url}"
        ),
        "notification_category": "course-related emails",
        "notification_footer": (
            "You are receiving this because general course-related "
            "emails are enabled."
        ),
    }


def _certificate_availability_metadata(enrollment):
    return {
        "source": "course-management-platform",
        "event": "certificate_availability",
        "preference_key": "email_course_updates",
        "cmp_preference_key": "email_course_updates",
        "course_slug": enrollment.course.slug,
        "enrollment_id": enrollment.pk,
        "user_id": enrollment.student_id,
    }


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

    urls = _certificate_availability_urls(enrollment)
    course = enrollment.course

    payload = {
        "audience": config.audience,
        "client": config.client,
        "email": email,
        "template_key": (
            email_templates.CERTIFICATE_AVAILABILITY_NOTIFICATION
        ),
        "category_tag": "course-updates",
        "idempotency_key": f"certificate-available:{enrollment.pk}",
        "context": _certificate_availability_context(enrollment, urls),
        "metadata": _certificate_availability_metadata(enrollment),
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

def datamailer_send_list_key(
    send_type: str,
    *,
    explicit_list_key: str,
    payload: dict[str, Any],
    response: dict[str, Any],
) -> str:
    if explicit_list_key:
        return explicit_list_key
    if send_type == DatamailerSendAuditType.RECIPIENT_LIST:
        recipient_list = response.get("recipient_list") or {}
        return recipient_list.get("key", "")
    if send_type == DatamailerSendAuditType.TRANSIENT_RECIPIENT_LIST:
        transient_list = response.get("transient_recipient_list") or {}
        if transient_list.get("key"):
            return transient_list["key"]
        list_data = payload.get("list") or {}
        return list_data.get("key", "")
    return ""

def datamailer_send_counts(
    send_type: str,
    payload: dict[str, Any],
    response: dict[str, Any],
) -> dict[str, int]:
    if send_type == DatamailerSendAuditType.TRANSACTIONAL:
        idempotent_replay_count = int(bool(response.get("idempotent_replay")))
        enqueued_count = int(bool(response.get("enqueued")))
        message = response.get("message") or {}
        skipped_count = int(message.get("status") == "skipped")
        created_count = int(bool(response) and not idempotent_replay_count)
        return {
            "intended_count": 1,
            "created_count": created_count,
            "enqueued_count": enqueued_count,
            "skipped_count": skipped_count,
            "idempotent_replay_count": idempotent_replay_count,
        }

    intended_count = 0
    if send_type == DatamailerSendAuditType.RECIPIENT_LIST:
        recipient_list = response.get("recipient_list") or {}
        intended_count = recipient_list.get("active_member_count") or 0
    elif send_type == DatamailerSendAuditType.TRANSIENT_RECIPIENT_LIST:
        transient_list = response.get("transient_recipient_list") or {}
        intended_count = transient_list.get("active_member_count") or 0
        if not intended_count:
            members = payload.get("members")
            if isinstance(members, list):
                intended_count = sum(
                    1 for member in members if member.get("status") != "removed"
                )

    return {
        "intended_count": int(intended_count or 0),
        "created_count": int(response.get("created_count") or 0),
        "enqueued_count": int(response.get("enqueued_count") or 0),
        "skipped_count": int(response.get("skipped_count") or 0),
        "idempotent_replay_count": int(
            response.get("idempotent_replay_count") or 0
        ),
    }
