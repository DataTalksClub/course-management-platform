from dataclasses import dataclass
from typing import List

from django.http import HttpRequest, HttpResponse

from django.utils import timezone
from django.shortcuts import render, get_object_or_404, redirect

from django.db.models import Prefetch

from courses.models import (
    Course,
    Enrollment,
    Project,
    ProjectSubmission,
    ProjectState,
    RegistrationCampaign,
    CourseRegistration,
    User,
    PeerReview,
    PeerReviewState,
)

from .course_list import (
    add_course_homepage_info,
    course_list as course_list,
)
from .course_calendar import course_calendar_view as course_calendar_view
from .course_enrollment import (
    enrollment_view as enrollment_view,
    update_enrollment_toggle as update_enrollment_toggle,
)
from .course_homeworks import (
    get_homeworks_for_course as get_homeworks_for_course,
    update_homework_with_additional_info as update_homework_with_additional_info,
)
from .course_leaderboard import (
    invalidate_leaderboard_cache as invalidate_leaderboard_cache,
    leaderboard_complaint_view as leaderboard_complaint_view,
    leaderboard_score_breakdown_view as leaderboard_score_breakdown_view,
    leaderboard_view as leaderboard_view,
)
from .course_project_submissions import (
    list_all_project_submissions_view as list_all_project_submissions_view,
)
from .dashboard import dashboard_view as dashboard_view


@dataclass(frozen=True)
class ProjectBadgeData:
    name: str
    css_class: str
    score: object = None


@dataclass(frozen=True)
class CoursePageData:
    course: Course
    user: object
    homeworks: list
    projects: list
    registration_campaign: object


def get_projects_for_course(
    course: Course, user: User
) -> List[Project]:
    if user.is_authenticated:
        queryset = ProjectSubmission.objects.filter(student=user)
    else:
        queryset = ProjectSubmission.objects.none()

    submissions_prefetch = Prefetch(
        "projectsubmission_set",
        queryset=queryset,
        to_attr="submissions",
    )

    projects = (
        Project.objects.filter(course=course)
        .prefetch_related(submissions_prefetch)
        .order_by("id")
    )

    for project in projects:
        update_project_with_additional_info(project)

    return list(projects)


def _project_days_until(due_date) -> int:
    now = timezone.now()
    if due_date > now:
        return (due_date - now).days
    return 0


def _base_project_badge(state):
    """Badge from a project's state alone, before any submission."""
    if state == ProjectState.CLOSED.value:
        return ProjectBadgeData("Closed", "bg-secondary")
    if state == ProjectState.COLLECTING_SUBMISSIONS.value:
        return ProjectBadgeData("Open", "bg-warning")
    return ProjectBadgeData("Not submitted", "bg-secondary")


def _submitted_mandatory_review_count(submission):
    return PeerReview.objects.filter(
        reviewer=submission,
        optional=False,
        state=PeerReviewState.SUBMITTED.value,
    ).count()


def _peer_review_project_badge(project, submission):
    completed_reviews_count = _submitted_mandatory_review_count(
        submission
    )
    if completed_reviews_count >= project.number_of_peers_to_evaluate:
        return ProjectBadgeData("Review completed", "bg-success")

    return ProjectBadgeData("Review", "bg-danger")


def _completed_project_badge(submission):
    score = submission.total_score
    if submission.passed:
        return ProjectBadgeData(f"Passed ({score})", "bg-success", score)

    return ProjectBadgeData(f"Failed ({score})", "bg-secondary", score)


def _submitted_project_badge(project, submission):
    """Badge override once a project has a submission."""
    state = project.state
    if state == ProjectState.COLLECTING_SUBMISSIONS.value:
        return ProjectBadgeData("Submitted", "bg-info")
    if state == ProjectState.PEER_REVIEWING.value:
        return _peer_review_project_badge(project, submission)
    if state == ProjectState.COMPLETED.value:
        return _completed_project_badge(submission)
    return None


def update_project_with_additional_info(project: Project) -> None:
    project.days_until_submission_due = _project_days_until(
        project.submission_due_date
    )
    project.days_until_pr_due = _project_days_until(
        project.peer_review_due_date
    )

    project.submitted = False
    project.score = None
    badge = _base_project_badge(project.state)
    project.badge_state_name = badge.name
    project.badge_css_class = badge.css_class

    if not project.submissions:
        return

    submission = project.submissions[0]
    project.submitted = True
    project.submitted_at = submission.submitted_at

    override = _submitted_project_badge(project, submission)
    if override is not None:
        project.badge_state_name = override.name
        project.badge_css_class = override.css_class
        project.score = override.score


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
        return _empty_course_enrollment_progress()

    return {
        "has_enrollment": True,
        "total_score": enrollment.total_score,
        "certificate_url": enrollment.certificate_url,
    }


def _empty_course_enrollment_progress() -> dict:
    return {
        "has_enrollment": False,
        "total_score": None,
        "certificate_url": None,
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
    context = {
        "course": data.course,
        "homeworks": data.homeworks,
        "projects": data.projects,
        "has_completed_projects": has_completed_projects(data.projects),
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


def course_registration_redirect_response(data: CoursePageData):
    if should_redirect_to_registration_campaign(
        registration_campaign=data.registration_campaign,
        homeworks=data.homeworks,
        projects=data.projects,
        user=data.user,
    ):
        return redirect(
            "registration_campaign",
            campaign_slug=data.registration_campaign.slug,
        )
    return None


def course_view(request: HttpRequest, course_slug: str) -> HttpResponse:
    data = course_page_data(course_slug, request.user)
    redirect_response = course_registration_redirect_response(data)
    if redirect_response is not None:
        return redirect_response

    context = course_page_context(data)
    return render(
        request,
        "courses/course.html",
        context,
    )
