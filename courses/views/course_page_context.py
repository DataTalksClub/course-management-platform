from dataclasses import dataclass

from django.conf import settings
from django.shortcuts import get_object_or_404
from django.utils import timezone

from courses.models.course import (
    Course,
    CourseRegistration,
    Enrollment,
    RegistrationCampaign,
)
from courses.models.project import ProjectState
from courses.referrals import invite_url_for_registration
from courses.registration_confirmation import user_unconfirmed_registrations
from courses.registration_counts import registered_people_count
from courses.registration_wall import (
    approved_registration_for_user,
    course_has_registration_wall,
    registration_wall_blocks_user,
    registration_wall_status_for_user,
)
from courses.views.course_homepage import (
    add_course_homepage_info,
    submitted_project_ids_for_user,
)
from courses.views.course_homeworks import get_homeworks_for_course
from courses.views.course_projects import get_projects_for_course


@dataclass(frozen=True)
class CoursePageData:
    course: Course
    user: object
    homeworks: list
    projects: list
    registration_campaign: object


def active_registration_campaign_for_course(
    course: Course,
) -> RegistrationCampaign | None:
    return (
        RegistrationCampaign.objects.filter(
            current_course=course,
            is_active=True,
        )
        .order_by("id")
        .first()
    )


def has_completed_projects(projects) -> bool:
    for project in projects:
        if project.state == ProjectState.COMPLETED.value:
            return True
    return False


def _authenticated_course_progress(
    user,
    course: Course,
    registration_campaign: RegistrationCampaign | None,
) -> dict:
    context = _course_enrollment_progress(user, course)
    context["has_registration"] = _has_course_registration(
        user,
        registration_campaign,
    )
    return context


def _course_enrollment_progress(user, course: Course) -> dict:
    try:
        enrollment = Enrollment.objects.get(
            student=user,
            course=course,
        )
    except Enrollment.DoesNotExist:
        return {
            "has_enrollment": False,
            "total_score": None,
            "certificate_url": None,
        }

    return {
        "has_enrollment": True,
        "total_score": enrollment.total_score,
        "certificate_url": enrollment.certificate_url,
    }

def _default_base_url() -> str:
    configured = getattr(settings, "SITE_URL", "")
    if configured:
        return configured.rstrip("/")
    from django.contrib.sites.models import Site

    return f"https://{Site.objects.get_current().domain}"


def _invite_url_for_user(
    user,
    course: Course,
    registration_campaign: RegistrationCampaign | None,
    base_url: str = "",
) -> str:
    """Personal shareable invite link for approved applicants, else "".

    Reuses ``invite_url_for_registration`` from ``courses.referrals`` so
    the main course page and approval emails produce the exact same URL.
    """
    if not user.is_authenticated:
        return ""
    registration = approved_registration_for_user(course, user)
    if registration is None or not registration.campaign_id:
        return ""
    if not registration.campaign.is_active:
        return ""
    resolved_base = (base_url or "").strip() or _default_base_url()
    return invite_url_for_registration(registration, resolved_base)


def _has_course_registration(
    user,
    registration_campaign: RegistrationCampaign | None,
) -> bool:
    if not registration_campaign:
        return False

    email = user.email or ""
    stripped_email = email.strip()
    email_normalized = stripped_email.lower()
    return CourseRegistration.objects.filter(
        campaign=registration_campaign,
        email_normalized=email_normalized,
    ).exists()


def course_user_context(
    user,
    course: Course,
    registration_campaign: RegistrationCampaign | None,
) -> dict:
    if not user.is_authenticated:
        return {
            "has_enrollment": False,
            "total_score": None,
            "certificate_url": None,
            "has_registration": False,
        }

    return _authenticated_course_progress(
        user,
        course,
        registration_campaign,
    )


def course_page_context(data: CoursePageData, base_url: str = "") -> dict:
    has_completed_course_projects = has_completed_projects(data.projects)
    context = {
        "course": data.course,
        "homeworks": data.homeworks,
        "projects": data.projects,
        "has_completed_projects": has_completed_course_projects,
        "is_authenticated": data.user.is_authenticated,
        "registration_campaign": data.registration_campaign,
    }
    user_context = course_user_context(
        data.user,
        data.course,
        data.registration_campaign,
    )
    context.update(user_context)
    context["registration_wall"] = course_has_registration_wall(data.course)
    context["registration_wall_blocked"] = registration_wall_blocks_user(
        data.course,
        data.user,
    )
    context["registration_wall_status"] = registration_wall_status_for_user(
        data.course,
        data.user,
    )
    context["registration_enrollment_missing"] = bool(
        context["registration_wall"]
        and context["registration_wall_status"]
        == CourseRegistration.Status.APPROVED.value
        and not context["has_enrollment"]
    )
    context["application_under_review"] = bool(
        context["registration_wall_blocked"]
        and context["registration_wall_status"]
        == CourseRegistration.Status.PENDING.value
    )
    context["registered_count"] = registered_people_count(data.course)
    context["invite_url"] = _invite_url_for_user(
        data.user,
        data.course,
        data.registration_campaign,
        base_url=base_url,
    )
    context["show_leaderboard"] = bool(
        data.course.first_homework_scored
        or Enrollment.objects.filter(
            course=data.course,
            bonus_points__gt=0,
        ).exists()
    )
    context["unconfirmed_registrations"] = user_unconfirmed_registrations(
        data.user,
        course=data.course,
    )
    return context


def course_page_data(course_slug: str, user) -> CoursePageData:
    course = get_object_or_404(Course, slug=course_slug)
    now = timezone.now()
    submitted_project_ids = submitted_project_ids_for_user([course], user)
    add_course_homepage_info(course, now, submitted_project_ids)
    homeworks = get_homeworks_for_course(course, user)
    projects = get_projects_for_course(course, user)
    registration_campaign = active_registration_campaign_for_course(
        course
    )
    return CoursePageData(
        course=course,
        user=user,
        homeworks=homeworks,
        projects=projects,
        registration_campaign=registration_campaign,
    )
