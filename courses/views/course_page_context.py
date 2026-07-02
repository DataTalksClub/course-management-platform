from dataclasses import dataclass

from django.shortcuts import get_object_or_404
from django.utils import timezone

from courses.models.course import (
    Course,
    CourseRegistration,
    Enrollment,
    RegistrationCampaign,
)
from courses.models.project import ProjectState
from courses.views.course_homepage import add_course_homepage_info
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


def should_redirect_to_registration_campaign(
    *,
    registration_campaign: RegistrationCampaign | None,
    homeworks,
    projects,
    user,
) -> bool:
    return (
        registration_campaign is not None
        and not homeworks
        and not projects
        and not user.is_staff
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


def course_page_context(data: CoursePageData) -> dict:
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
    return context


def course_page_data(course_slug: str, user) -> CoursePageData:
    course = get_object_or_404(Course, slug=course_slug)
    now = timezone.now()
    add_course_homepage_info(course, now)
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
