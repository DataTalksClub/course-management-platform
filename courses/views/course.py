from collections import defaultdict
from dataclasses import dataclass
from typing import List

from django.http import HttpRequest, HttpResponse

from django.utils import timezone
from django.shortcuts import render, get_object_or_404, redirect

from django.db.models import Count, Prefetch

from courses.models import (
    Course,
    Homework,
    Submission,
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

from .course_calendar import course_calendar_view as course_calendar_view
from .course_enrollment import (
    enrollment_view as enrollment_view,
    update_enrollment_toggle as update_enrollment_toggle,
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
class CourseListCourses:
    courses: list
    active_courses: list
    finished_courses: list
    archive_courses_by_year: dict


@dataclass(frozen=True)
class CoursePageData:
    course: Course
    user: object
    homeworks: list
    projects: list
    registration_campaign: object


ASSIGNMENT_TYPE_ORDER = {
    "homework": 1,
    "project": 2,
    "peer_review": 3,
}


COURSE_OUTCOMES = {
    "de": {
        "outcome": "Build reliable data pipelines, warehouses, and batch or streaming workflows.",
    },
    "ml": {
        "outcome": "Train, evaluate, deploy, and operate practical machine learning systems.",
    },
    "llm": {
        "outcome": "Build search, retrieval, evaluation, and application workflows with language models.",
    },
    "mlops": {
        "outcome": "Ship models with experiment tracking, orchestration, deployment, and monitoring.",
    },
    "sma": {
        "outcome": "Work with market data, analytics workflows, and practical financial modeling.",
    },
    "ai-dev-tools": {
        "outcome": "Use modern AI tooling to build, inspect, and ship software projects.",
    },
}


def get_course_outcome(course: Course) -> str:
    if course.description:
        return course.description

    for slug_prefix, presentation in COURSE_OUTCOMES.items():
        if course.slug.startswith(slug_prefix):
            return presentation["outcome"]

    return "Practical lessons, homework, projects, and peer review."


def course_year(course: Course) -> str:
    title_parts = course.title.split()
    reversed_title_parts = reversed(title_parts)
    for part in reversed_title_parts:
        if part.isdigit() and len(part) == 4:
            return part
    return "Archive"


def course_duration_label(course: Course) -> str:
    if not course.start_date or not course.end_date:
        return "TBA"

    duration_days = (course.end_date - course.start_date).days + 1
    duration_days = max(duration_days, 1)

    if duration_days >= 14:
        duration_weeks = round(duration_days / 7)
        return f"{duration_weeks} weeks"

    if duration_days == 1:
        return "1 day"

    return f"{duration_days} days"


def get_course_assignments(course: Course) -> list[dict]:
    assignments = []

    homeworks = course.homework_set.all()
    for homework in homeworks:
        homework_assignment = homework_assignment_record(homework)
        assignments.append(homework_assignment)

    projects = course.project_set.all()
    for project in projects:
        project_assignment = project_assignment_record(project)
        assignments.append(project_assignment)

        peer_review_assignment = peer_review_assignment_record(project)
        assignments.append(peer_review_assignment)

    return sorted(assignments, key=course_assignment_sort_key)


def homework_assignment_record(homework) -> dict:
    return {
        "type": "homework",
        "label": "Homework",
        "title": homework.title,
        "due_date": homework.due_date,
    }


def project_assignment_record(project) -> dict:
    return {
        "type": "project",
        "label": "Project",
        "title": project.title,
        "due_date": project.submission_due_date,
    }


def peer_review_assignment_record(project) -> dict:
    return {
        "type": "peer_review",
        "label": "Peer review",
        "title": project.title,
        "due_date": project.peer_review_due_date,
    }


def course_assignment_sort_key(assignment):
    return (
        assignment["due_date"],
        ASSIGNMENT_TYPE_ORDER[assignment["type"]],
    )


def current_assignment_info(course: Course, now) -> tuple[str, dict | None]:
    assignments = get_course_assignments(course)

    if not assignments:
        return "Current assignment", None

    upcoming_assignments = []
    for assignment in assignments:
        if assignment["due_date"] >= now:
            upcoming_assignments.append(assignment)

    if upcoming_assignments:
        return "Next assignment", upcoming_assignments[0]

    return "Last assignment", assignments[-1]


def add_course_homepage_info(course: Course, now) -> None:
    today = timezone.localdate(now)

    course.home_outcome = get_course_outcome(course)
    course.home_year = course_year(course)
    course.home_duration_label = course_duration_label(course)
    course.home_registration_open = (
        bool(course.registration_url)
        and bool(course.start_date)
        and today < course.start_date
    )
    (
        course.home_current_assignment_label,
        course.home_current_assignment,
    ) = current_assignment_info(course, now)


def attach_registration_campaigns(courses) -> None:
    course_ids = []
    for course in courses:
        course_ids.append(course.id)
    campaigns = RegistrationCampaign.objects.filter(
        current_course_id__in=course_ids,
        is_active=True,
    ).order_by("id")
    campaign_by_course_id = {}
    for campaign in campaigns:
        campaign_by_course_id.setdefault(campaign.current_course_id, campaign)

    for course in courses:
        course.registration_campaign = campaign_by_course_id.get(course.id)


def _registration_campaign_ids(courses):
    campaign_ids = []
    for course in courses:
        registration_campaign = getattr(course, "registration_campaign", None)
        if registration_campaign:
            campaign_ids.append(registration_campaign.id)
    return campaign_ids


def _normalized_user_email(user) -> str:
    return (user.email or "").strip().lower()


def _registered_campaign_ids(campaign_ids, user):
    return set(
        CourseRegistration.objects.filter(
            campaign_id__in=campaign_ids,
            email_normalized=_normalized_user_email(user),
        ).values_list("campaign_id", flat=True)
    )


def _mark_registered_course(course, registered_campaign_ids) -> None:
    campaign = getattr(course, "registration_campaign", None)
    course.is_registered = (
        campaign is not None and campaign.id in registered_campaign_ids
    )


def mark_registered_courses(courses, user) -> None:
    if not user.is_authenticated:
        return

    campaign_ids = _registration_campaign_ids(courses)
    registered_campaign_ids = _registered_campaign_ids(campaign_ids, user)
    for course in courses:
        _mark_registered_course(course, registered_campaign_ids)


def mark_enrolled_courses(courses, user) -> None:
    if not user.is_authenticated:
        return

    course_ids = []
    for course in courses:
        course_ids.append(course.id)
    enrolled_course_ids = set(
        Enrollment.objects.filter(
            student=user,
            course_id__in=course_ids,
        ).values_list("course_id", flat=True)
    )

    for course in courses:
        course.is_enrolled = course.id in enrolled_course_ids


def _visible_course_list_queryset():
    return (
        Course.objects.filter(visible=True)
        .annotate(
            homework_count=Count("homework", distinct=True),
            project_count=Count("project", distinct=True),
            learner_count=Count("enrollment", distinct=True),
        )
        .prefetch_related("homework_set", "project_set")
        .order_by("-id")
    )


def _split_courses_by_status(courses, now):
    active_courses = []
    finished_courses = []
    archive_courses_by_year = defaultdict(list)

    for course in courses:
        add_course_homepage_info(course, now)

        if course.finished:
            finished_courses.append(course)
            archive_courses_by_year[course.home_year].append(course)
        else:
            active_courses.append(course)

    return CourseListCourses(
        courses,
        active_courses,
        finished_courses,
        archive_courses_by_year,
    )


def _featured_course(active_courses):
    for course in active_courses:
        if not course.title.lower().startswith("fake"):
            return course

    if active_courses:
        return active_courses[0]

    return None


def _course_archive_groups(archive_courses_by_year):
    archive_years = sorted(
        archive_courses_by_year.keys(),
        key=lambda year: (year == "Archive", year),
        reverse=True,
    )
    if "Archive" in archive_years:
        archive_years.remove("Archive")
        archive_years.append("Archive")

    archive_groups = []
    for year in archive_years:
        archive_group = {
            "year": year,
            "courses": archive_courses_by_year[year],
        }
        archive_groups.append(archive_group)
    return archive_groups


def _course_home_stats(courses, active_courses, finished_courses):
    homework_count = 0
    project_count = 0
    for course in courses:
        homework_count += course.homework_count
        project_count += course.project_count

    return {
        "active_courses": len(active_courses),
        "archive_courses": len(finished_courses),
        "homeworks": homework_count,
        "projects": project_count,
    }


def _other_active_courses(active_courses, featured_course):
    other_active_courses = []
    for course in active_courses:
        if course != featured_course:
            other_active_courses.append(course)
    return other_active_courses


def _prepare_course_list_courses(user):
    courses = list(_visible_course_list_queryset())
    course_groups = _split_courses_by_status(courses, timezone.now())

    mark_enrolled_courses(course_groups.courses, user)
    attach_registration_campaigns(course_groups.courses)
    mark_registered_courses(course_groups.courses, user)

    return course_groups


def _course_list_context(user):
    course_groups = _prepare_course_list_courses(user)
    featured_course = _featured_course(course_groups.active_courses)

    return {
        "active_courses": course_groups.active_courses,
        "archive_groups": _course_archive_groups(
            course_groups.archive_courses_by_year
        ),
        "featured_course": featured_course,
        "finished_courses": course_groups.finished_courses,
        "other_active_courses": _other_active_courses(
            course_groups.active_courses,
            featured_course,
        ),
        "home_stats": _course_home_stats(
            course_groups.courses,
            course_groups.active_courses,
            course_groups.finished_courses,
        ),
    }


def course_list(request):
    context = _course_list_context(request.user)
    return render(
        request,
        "courses/course_list.html",
        context,
    )


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

    email_normalized = (user.email or "").strip().lower()
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
    context.update(
        course_user_context(
            data.user,
            data.course,
            data.registration_campaign,
        )
    )
    return context


def course_page_data(course_slug: str, user) -> CoursePageData:
    course = get_object_or_404(Course, slug=course_slug)
    add_course_homepage_info(course, timezone.now())
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


def get_homeworks_for_course(course: Course, user) -> List[Homework]:
    if user.is_authenticated:
        queryset = Submission.objects.filter(student=user)
    else:
        queryset = Submission.objects.none()

    submissions_prefetch = Prefetch(
        "submission_set", queryset=queryset, to_attr="submissions"
    )

    homeworks = (
        Homework.objects.filter(course=course)
        .prefetch_related(submissions_prefetch)
        .order_by("due_date")
    )

    for hw in homeworks:
        update_homework_with_additional_info(hw)

    return list(homeworks)


def update_homework_with_additional_info(homework: Homework) -> None:
    days_until_due = 0

    if homework.due_date > timezone.now():
        days_until_due = (homework.due_date - timezone.now()).days + 1

    homework.days_until_due = days_until_due
    homework.submitted = False
    homework.score = None

    if not homework.submissions:
        return

    submission = homework.submissions[0]

    homework.submitted = True
    if homework.is_scored():
        homework.score = submission.total_score
    else:
        homework.submitted_at = submission.submitted_at
