import logging
import statistics

from collections import defaultdict
from dataclasses import dataclass
from datetime import timedelta, timezone as datetime_timezone
from typing import List

from django.http import HttpRequest, HttpResponse, JsonResponse

from django.core.paginator import Paginator
from django.utils import timezone
from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse

from django.db.models import Prefetch, Value, Count, Q, Sum
from django.db.models import Case, When, IntegerField
from django.db.models.functions import Coalesce

from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.core.cache import cache

from courses.models import (
    Course,
    Homework,
    HomeworkState,
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

from .forms import EnrollmentForm, LeaderboardComplaintForm

logger = logging.getLogger(__name__)

LEADERBOARD_PAGE_SIZE = 100
PROJECT_SUBMISSIONS_PAGE_SIZE = 25


@dataclass(frozen=True)
class ProjectDeadlineEventSpec:
    uid_suffix: str
    event_type: str
    deadline: object


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
    """Badge (name, css) from a project's state alone, before any submission."""
    if state == ProjectState.CLOSED.value:
        return "Closed", "bg-secondary"
    if state == ProjectState.COLLECTING_SUBMISSIONS.value:
        return "Open", "bg-warning"
    return "Not submitted", "bg-secondary"


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
        return "Review completed", "bg-success", None

    return "Review", "bg-danger", None


def _completed_project_badge(submission):
    score = submission.total_score
    if submission.passed:
        return f"Passed ({score})", "bg-success", score

    return f"Failed ({score})", "bg-secondary", score


def _submitted_project_badge(project, submission):
    """Badge override (name, css, score) once a project has a submission.

    Returns None for states that keep the base badge (e.g. still CLOSED).
    """
    state = project.state
    if state == ProjectState.COLLECTING_SUBMISSIONS.value:
        return "Submitted", "bg-info", None
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
    project.badge_state_name, project.badge_css_class = (
        _base_project_badge(project.state)
    )

    if not project.submissions:
        return

    submission = project.submissions[0]
    project.submitted = True
    project.submitted_at = submission.submitted_at

    override = _submitted_project_badge(project, submission)
    if override is not None:
        (
            project.badge_state_name,
            project.badge_css_class,
            project.score,
        ) = override


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
    return any(
        project.state == ProjectState.COMPLETED.value
        for project in projects
    )


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
        course,
        user,
        homeworks,
        projects,
        registration_campaign,
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

    return render(
        request,
        "courses/course.html",
        course_page_context(data),
    )


def escape_ics_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace(";", "\\;")
        .replace(",", "\\,")
    )


def format_ics_datetime(value) -> str:
    if timezone.is_naive(value):
        value = timezone.make_aware(
            value, timezone.get_current_timezone()
        )

    value = value.astimezone(datetime_timezone.utc)
    return value.strftime("%Y%m%dT%H%M%SZ")


def calendar_event(
    *,
    uid: str,
    summary: str,
    start,
    url: str,
    description: str,
    dtstamp,
) -> list[str]:
    end = start + timedelta(minutes=30)

    return [
        "BEGIN:VEVENT",
        f"UID:{escape_ics_text(uid)}",
        f"DTSTAMP:{format_ics_datetime(dtstamp)}",
        f"DTSTART:{format_ics_datetime(start)}",
        f"DTEND:{format_ics_datetime(end)}",
        f"SUMMARY:{escape_ics_text(summary)}",
        f"DESCRIPTION:{escape_ics_text(description)}",
        f"URL:{escape_ics_text(url)}",
        "END:VEVENT",
    ]


def _homework_calendar_events(request, course, dtstamp) -> list[list[str]]:
    homeworks = Homework.objects.filter(course=course).order_by("due_date")
    events = []
    for homework in homeworks:
        url = request.build_absolute_uri(
            reverse(
                "homework",
                kwargs={
                    "course_slug": course.slug,
                    "homework_slug": homework.slug,
                },
            )
        )
        event = calendar_event(
            uid=f"homework-{homework.id}@courses.datatalks.club",
            summary=f"{course.title}: {homework.title} deadline",
            start=homework.due_date,
            url=url,
            description=(
                f"Homework deadline for {homework.title}. "
                f"Open the assignment: {url}"
            ),
            dtstamp=dtstamp,
        )
        events.append(event)
    return events


def _project_detail_url(request, course, project) -> str:
    return request.build_absolute_uri(
        reverse(
            "project",
            kwargs={
                "course_slug": course.slug,
                "project_slug": project.slug,
            },
        )
    )


def _project_deadline_calendar_event(
    *,
    course,
    project,
    uid_suffix: str,
    event_type: str,
    deadline,
    url: str,
    dtstamp,
) -> list[str]:
    return calendar_event(
        uid=f"project-{project.id}-{uid_suffix}@courses.datatalks.club",
        summary=f"{course.title}: {project.title} {event_type} deadline",
        start=deadline,
        url=url,
        description=(
            f"Project {event_type} deadline for {project.title}. "
            f"Open the project: {url}"
        ),
        dtstamp=dtstamp,
    )


def _project_deadline_calendar_events(
    course, project, url, dtstamp
) -> list[list[str]]:
    deadlines = (
        ProjectDeadlineEventSpec(
            uid_suffix="submission",
            event_type="submission",
            deadline=project.submission_due_date,
        ),
        ProjectDeadlineEventSpec(
            uid_suffix="peer-review",
            event_type="peer review",
            deadline=project.peer_review_due_date,
        ),
    )
    events = []
    for deadline in deadlines:
        event = _project_deadline_calendar_event(
            course=course,
            project=project,
            uid_suffix=deadline.uid_suffix,
            event_type=deadline.event_type,
            deadline=deadline.deadline,
            url=url,
            dtstamp=dtstamp,
        )
        events.append(event)
    return events


def _project_calendar_events(request, course, dtstamp) -> list[list[str]]:
    projects = Project.objects.filter(course=course).order_by(
        "submission_due_date",
        "peer_review_due_date",
    )
    events = []
    for project in projects:
        project_url = _project_detail_url(request, course, project)
        project_events = _project_deadline_calendar_events(
            course, project, project_url, dtstamp
        )
        events.extend(project_events)
    return events


def _course_calendar_lines(course, events):
    return [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//DataTalks.Club//Course Management Platform//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escape_ics_text(course.title)} deadlines",
        *events,
        "END:VCALENDAR",
    ]


def course_calendar_view(
    request: HttpRequest,
    course_slug: str,
) -> HttpResponse:
    course = get_object_or_404(Course, slug=course_slug, visible=True)
    dtstamp = timezone.now()
    nested_events = []
    homework_events = _homework_calendar_events(request, course, dtstamp)
    nested_events.extend(homework_events)
    project_events = _project_calendar_events(request, course, dtstamp)
    nested_events.extend(project_events)

    events = []
    for event_lines in nested_events:
        for line in event_lines:
            events.append(line)
    calendar_lines = _course_calendar_lines(course, events)

    response = HttpResponse(
        "\r\n".join(calendar_lines) + "\r\n",
        content_type="text/calendar; charset=utf-8",
    )
    response["Content-Disposition"] = (
        f'inline; filename="{course.slug}-deadlines.ics"'
    )
    return response


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


def _current_student_leaderboard_enrollment(course, user):
    if user.is_authenticated:
        try:
            enrollment = Enrollment.objects.get(
                student=user,
                course=course,
            )
            return enrollment, enrollment.id
        except Enrollment.DoesNotExist:
            pass

    return None, None


def _completed_project_submissions_prefetch():
    return Prefetch(
        "projectsubmission_set",
        queryset=ProjectSubmission.objects.filter(
            project__state=ProjectState.COMPLETED.value,
            volunteer_review_only=False,
        )
        .select_related("project")
        .order_by("project__id"),
        to_attr="completed_project_submissions",
    )


def _serialize_leaderboard_enrollment(enrollment):
    passed_projects = []
    completed_submissions = enrollment.completed_project_submissions
    for index, submission in enumerate(completed_submissions, 1):
        if not submission.passed:
            continue
        passed_project = {
            "title": submission.project.title,
            "slug": submission.project.slug,
            "attempt": index,
            "medal_index": ((index - 1) % 5) + 1,
        }
        passed_projects.append(passed_project)

    return {
        "id": enrollment.id,
        "display_name": enrollment.display_name,
        "total_score": enrollment.total_score,
        "position_on_leaderboard": enrollment.position_on_leaderboard,
        "passed_projects": passed_projects,
    }


def _build_leaderboard_data(course, cache_key):
    logger.info(f"Cache miss for leaderboard of course {course.slug}")
    enrollments = (
        Enrollment.objects.filter(
            course=course,
            display_on_leaderboard=True,
        )
        .select_related("student")
        .prefetch_related(_completed_project_submissions_prefetch())
        .order_by(
            Coalesce("position_on_leaderboard", Value(999999)),
            "id",
        )
    )
    # Store dictionaries in cache to avoid stale model instances.
    enrollments_data = []
    for enrollment in enrollments:
        enrollment_data = _serialize_leaderboard_enrollment(enrollment)
        enrollments_data.append(enrollment_data)
    cache.set(cache_key, enrollments_data, 3600)
    return enrollments_data


def _leaderboard_cache_missing_current_student(
    enrollments_data,
    current_student_enrollment,
    current_student_enrollment_id,
):
    if current_student_enrollment_id is None:
        return False
    if not current_student_enrollment.display_on_leaderboard:
        return False

    return not any(
        enrollment["id"] == current_student_enrollment_id
        for enrollment in enrollments_data
    )


def _get_leaderboard_data(
    course,
    cache_key,
    current_student_enrollment,
    current_student_enrollment_id,
):
    enrollments_data = cache.get(cache_key)

    if enrollments_data is None:
        return _build_leaderboard_data(course, cache_key)

    logger.info(f"Cache hit for leaderboard of course {course.slug}")
    if _leaderboard_cache_missing_current_student(
        enrollments_data,
        current_student_enrollment,
        current_student_enrollment_id,
    ):
        return _build_leaderboard_data(course, cache_key)

    return enrollments_data


def _current_student_page_number(
    enrollments_data,
    current_student_enrollment,
    current_student_enrollment_id,
):
    if (
        current_student_enrollment_id is None
        or not current_student_enrollment.display_on_leaderboard
    ):
        return None

    for index, enrollment in enumerate(enrollments_data):
        if enrollment["id"] == current_student_enrollment_id:
            return (index // LEADERBOARD_PAGE_SIZE) + 1

    return None


def leaderboard_view(request, course_slug: str):
    course = get_object_or_404(Course, slug=course_slug)
    current_student_enrollment, current_student_enrollment_id = (
        _current_student_leaderboard_enrollment(course, request.user)
    )

    cache_key = f"leaderboard:{course.id}"
    enrollments_data = _get_leaderboard_data(
        course,
        cache_key,
        current_student_enrollment,
        current_student_enrollment_id,
    )

    paginator = Paginator(enrollments_data, LEADERBOARD_PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))
    enrollments_page = page_obj.object_list

    current_student_page_number = _current_student_page_number(
        enrollments_data,
        current_student_enrollment,
        current_student_enrollment_id,
    )

    context = {
        "enrollments": enrollments_page,
        "page_obj": page_obj,
        "page_range": paginator.get_elided_page_range(page_obj.number),
        "total_enrollments": paginator.count,
        "course": course,
        "current_student_enrollment": current_student_enrollment,
        "current_student_enrollment_id": current_student_enrollment_id,
        "current_student_page_number": current_student_page_number,
    }

    return render(request, "courses/leaderboard.html", context)


def invalidate_leaderboard_cache(course_id: int) -> None:
    cache.delete(f"leaderboard:{course_id}")
    version_key = f"leaderboard_cache_version:{course_id}"
    cache.set(version_key, cache.get(version_key, 1) + 1, None)


def leaderboard_score_breakdown_view(
    request, course_slug: str, enrollment_id: int
):
    enrollment = get_object_or_404(
        Enrollment.objects.select_related("student", "course"),
        id=enrollment_id,
        course__slug=course_slug,
    )
    context = _leaderboard_score_breakdown_context(enrollment, request.user)

    return render(
        request, "courses/leaderboard_score_breakdown.html", context
    )


def _leaderboard_score_breakdown_context(enrollment, user):
    is_own_record = (
        user.is_authenticated and user.id == enrollment.student_id
    )
    public_profile = (
        enrollment.student if enrollment.display_public_profile else None
    )

    return {
        "enrollment": enrollment,
        "public_profile": public_profile,
        "show_public_profile_settings_link": (
            is_own_record and public_profile is None
        ),
        "submissions": _leaderboard_homework_submissions(enrollment),
        "project_submissions": _leaderboard_project_submissions(enrollment),
    }


def _leaderboard_homework_state_order():
    return Case(
        When(homework__state=HomeworkState.SCORED.value, then=Value(0)),
        When(homework__state=HomeworkState.OPEN.value, then=Value(1)),
        When(homework__state=HomeworkState.CLOSED.value, then=Value(2)),
        default=Value(3),
        output_field=IntegerField(),
    )


def _leaderboard_homework_submissions(enrollment):
    return Submission.objects.filter(
        enrollment=enrollment
    ).order_by(_leaderboard_homework_state_order(), "homework__id")


def _leaderboard_project_submissions(enrollment):
    return ProjectSubmission.objects.filter(
        enrollment=enrollment,
        volunteer_review_only=False,
    ).order_by("project__id")


@login_required
def leaderboard_complaint_view(
    request, course_slug: str, enrollment_id: int
):
    enrollment = get_object_or_404(
        Enrollment.objects.select_related("course", "student"),
        id=enrollment_id,
        course__slug=course_slug,
    )

    if request.method == "POST":
        form = LeaderboardComplaintForm(request.POST)
        if form.is_valid():
            complaint = form.save(commit=False)
            complaint.enrollment = enrollment
            complaint.reporter = request.user
            complaint.save()
            messages.success(
                request,
                "Thanks. The course team will review this leaderboard record.",
            )
            return redirect(
                "leaderboard_score_breakdown",
                course_slug=course_slug,
                enrollment_id=enrollment.id,
            )
    else:
        form = LeaderboardComplaintForm()

    context = {
        "enrollment": enrollment,
        "course": enrollment.course,
        "form": form,
    }
    return render(request, "courses/leaderboard_complaint.html", context)


@login_required
@require_POST
def update_enrollment_toggle(request, course_slug):
    course = get_object_or_404(Course, slug=course_slug)
    enrollment, _ = Enrollment.objects.get_or_create(
        student=request.user,
        course=course,
    )

    field = request.POST.get("field", "")
    value = request.POST.get("value", "")
    if field not in {"display_on_leaderboard", "display_public_profile"}:
        return JsonResponse(
            {"error": "Unsupported enrollment setting."},
            status=400,
        )

    previous_display_on_leaderboard = enrollment.display_on_leaderboard
    enabled = value.lower() in {"1", "true", "yes", "on"}
    setattr(enrollment, field, enabled)
    enrollment.save(update_fields=[field])

    if (
        field == "display_on_leaderboard"
        and previous_display_on_leaderboard != enabled
    ):
        invalidate_leaderboard_cache(course.id)

    return JsonResponse(
        {
            "field": field,
            "value": enabled,
        }
    )


def _enrollment_context(course, enrollment, form):
    return {
        "form": form,
        "course": course,
        "enrollment": enrollment,
    }


def _render_enrollment_form(request, course, enrollment, form):
    return render(
        request,
        "courses/enrollment.html",
        _enrollment_context(course, enrollment, form),
    )


def _save_enrollment_form(form, course, enrollment) -> None:
    previous_display_on_leaderboard = enrollment.display_on_leaderboard
    form.save()
    if previous_display_on_leaderboard != form.instance.display_on_leaderboard:
        invalidate_leaderboard_cache(course.id)


def _handle_enrollment_post(request, course, enrollment, course_slug):
    form = EnrollmentForm(
        request.POST,
        instance=enrollment,
        user=request.user,
    )
    if form.is_valid():
        _save_enrollment_form(form, course, enrollment)
        return redirect("course", course_slug=course_slug)

    return _render_enrollment_form(request, course, enrollment, form)


@login_required
def enrollment_view(request, course_slug):
    course = get_object_or_404(Course, slug=course_slug)

    enrollment, _ = Enrollment.objects.get_or_create(
        student=request.user,
        course=course,
    )

    if request.method == "POST":
        return _handle_enrollment_post(
            request, course, enrollment, course_slug
        )

    form = EnrollmentForm(instance=enrollment, user=request.user)
    return _render_enrollment_form(request, course, enrollment, form)


def list_all_project_submissions_view(request, course_slug: str):
    course = get_object_or_404(Course, slug=course_slug)
    submissions_page = _all_project_submissions_page(course, request)
    context = _all_project_submissions_context(
        course,
        _projects_with_submission_counts(course),
        submissions_page,
        request.user,
    )

    return render(request, "projects/list_all.html", context)


def _projects_with_submission_counts(course):
    return (
        Project.objects.filter(course=course)
        .annotate(
            submissions_count=Count(
                "projectsubmission",
                filter=Q(projectsubmission__volunteer_review_only=False),
            )
        )
        .order_by("id")
    )


def _all_project_submissions(course):
    return (
        ProjectSubmission.objects.filter(
            project__course=course,
            volunteer_review_only=False,
        )
        .select_related("project", "enrollment")
        .annotate(
            vote_count=Count("votes"),
            display_score=_project_submission_display_score(),
        )
        .order_by("-vote_count", "-display_score", "project__id", "submitted_at")
    )


def _project_submission_display_score():
    return Case(
        When(
            project__state=ProjectState.COMPLETED.value,
            then="project_score",
        ),
        default=Value(-1),
        output_field=IntegerField(),
    )


def _all_project_submissions_page(course, request):
    return Paginator(
        _all_project_submissions(course), PROJECT_SUBMISSIONS_PAGE_SIZE
    ).get_page(request.GET.get("page"))


def _all_project_submissions_context(
    course,
    projects,
    submissions_page,
    user,
):
    return {
        "course": course,
        "projects": projects,
        "submissions": submissions_page.object_list,
        "submissions_page": submissions_page,
        "page_range": submissions_page.paginator.get_elided_page_range(
            submissions_page.number
        ),
        "is_authenticated": user.is_authenticated,
    }


def _safe_quartiles(data):
    """Return (q25, median, q75), or (None, None, None) if too little data."""
    if len(data) < 3:
        return None, None, None
    try:
        q25, median, q75 = statistics.quantiles(data, n=4)
        return q25, median, q75
    except statistics.StatisticsError:
        return None, None, None


def _format_median(value):
    """Format a median: whole numbers without decimals, else one decimal."""
    if not value:
        return None
    if value % 1 == 0:
        return f"{value:.0f}"
    return f"{value:.1f}"


def _dashboard_project_stats(course, total_enrollments):
    """Project-submission aggregates for the course dashboard."""
    project_submissions = _dashboard_project_submission_rows(course)
    completion_rate = _project_completion_rate(
        project_submissions,
        total_enrollments,
    )
    time_spent = _project_submission_values(
        project_submissions,
        "time_spent",
    )
    scores = _project_submission_values(project_submissions, "total_score")
    pass_count, fail_count = _project_pass_fail_counts(project_submissions)
    time_q25, time_median, time_q75 = _safe_quartiles(time_spent)
    score_q25, score_median, score_q75 = _safe_quartiles(scores)

    return {
        "project_completion_rate": round(completion_rate, 1),
        "project_time_q25": time_q25,
        "project_time_median": time_median,
        "project_time_q75": time_q75,
        "project_score_q25": score_q25,
        "project_score_median": score_median,
        "project_score_q75": score_q75,
        "project_pass_count": pass_count,
        "project_fail_count": fail_count,
        "project_total_submissions": pass_count + fail_count,
    }


def _dashboard_project_submission_rows(course):
    return list(
        ProjectSubmission.objects.filter(project__course=course)
        .select_related("project", "enrollment")
        .values("enrollment_id", "time_spent", "total_score", "passed")
    )


def _project_completion_rate(project_submissions, total_enrollments):
    if total_enrollments <= 0:
        return 0

    return (
        len(_project_submission_enrollment_ids(project_submissions))
        / total_enrollments
        * 100
    )


def _project_submission_enrollment_ids(project_submissions):
    enrollment_ids = set()
    for submission in project_submissions:
        enrollment_ids.add(submission["enrollment_id"])
    return enrollment_ids


def _project_submission_values(project_submissions, field_name):
    values = []
    for submission in project_submissions:
        value = submission[field_name]
        if value is not None:
            values.append(value)
    return values


def _project_pass_fail_counts(project_submissions):
    pass_count = 0
    for submission in project_submissions:
        if submission["passed"]:
            pass_count += 1
    fail_count = len(project_submissions) - pass_count
    return pass_count, fail_count


def _submission_values(submissions, field_name):
    values = []
    for submission in submissions:
        value = submission[field_name]
        if value is not None:
            values.append(value)
    return values


def _dashboard_completion_rate(submissions_count, total_enrollments):
    if total_enrollments <= 0:
        return 0.0
    return round(submissions_count / total_enrollments * 100, 1)


def _dashboard_total_homework_times(hw_submissions):
    total_times = []
    for submission in hw_submissions:
        lectures_time = submission["time_spent_lectures"]
        homework_time = submission["time_spent_homework"]
        if lectures_time is None or homework_time is None:
            continue
        total_time = lectures_time + homework_time
        total_times.append(total_time)
    return total_times


def _quartile_fields(prefix, values):
    q25, median, q75 = _safe_quartiles(values)
    return {
        f"{prefix}_q25": q25,
        f"{prefix}_median": median,
        f"{prefix}_q75": q75,
        f"{prefix}_median_formatted": _format_median(median),
    }


def _dashboard_homework_time_stats(hw_submissions):
    stats = {}
    stats.update(
        _quartile_fields(
            "time_lecture",
            _submission_values(hw_submissions, "time_spent_lectures"),
        )
    )
    stats.update(
        _quartile_fields(
            "time_homework",
            _submission_values(hw_submissions, "time_spent_homework"),
        )
    )
    stats.update(
        _quartile_fields(
            "time_total",
            _dashboard_total_homework_times(hw_submissions),
        )
    )
    return stats


def _dashboard_homework_score_ratio(homework, hw_submissions):
    questions_scores = _submission_values(hw_submissions, "questions_score")
    _, questions_score_median, _ = _safe_quartiles(questions_scores)
    max_questions_score = homework.max_questions_score
    score_ratio = (
        questions_score_median / max_questions_score
        if questions_score_median is not None and max_questions_score
        else None
    )
    return questions_score_median, max_questions_score, score_ratio


def _dashboard_homework_score_stats(homework, hw_submissions):
    score_q25, score_median, score_q75 = _safe_quartiles(
        _submission_values(hw_submissions, "total_score")
    )
    questions_score_median, max_questions_score, score_ratio = (
        _dashboard_homework_score_ratio(homework, hw_submissions)
    )
    return {
        "score_q25": score_q25,
        "score_median": score_median,
        "score_q75": score_q75,
        "questions_score_median": questions_score_median,
        "max_questions_score": max_questions_score,
        "score_ratio": score_ratio,
        "score_ratio_pct": (
            round(score_ratio * 100, 1)
            if score_ratio is not None
            else None
        ),
    }


def _dashboard_homework_stat(homework, hw_submissions, total_enrollments):
    """Per-homework statistics row for the dashboard."""
    time_stats = _dashboard_homework_time_stats(hw_submissions)
    score_stats = _dashboard_homework_score_stats(homework, hw_submissions)

    return {
        "homework": homework,
        "submissions_count": len(hw_submissions),
        "completion_rate": _dashboard_completion_rate(
            len(hw_submissions),
            total_enrollments,
        ),
        **time_stats,
        **score_stats,
    }


def _dashboard_homework_submissions_by_homework(all_hw_submissions):
    hw_submissions_by_homework = defaultdict(list)
    for submission in all_hw_submissions:
        hw_submissions_by_homework[submission["homework_id"]].append(
            submission
        )
    return hw_submissions_by_homework


def _dashboard_homework_stat_rows(
    homeworks,
    hw_submissions_by_homework,
    total_enrollments,
):
    stat_rows = []
    for homework in homeworks:
        submissions = hw_submissions_by_homework.get(homework.id, [])
        stat_row = _dashboard_homework_stat(
            homework,
            submissions,
            total_enrollments,
        )
        stat_rows.append(stat_row)
    return stat_rows


def _dashboard_homework_difficulty_stats(homework_stats):
    difficulty_stats = []
    for hw_stat in homework_stats:
        if hw_stat["score_ratio"] is not None:
            difficulty_stats.append(hw_stat)
    difficulty_stats.sort(
        key=lambda hw_stat: (
            hw_stat["score_ratio"],
            -hw_stat["submissions_count"],
            hw_stat["homework"].title,
        )
    )
    for rank, hw_stat in enumerate(difficulty_stats, start=1):
        hw_stat["difficulty_rank"] = rank

    return difficulty_stats


def _dashboard_homework_stats(homeworks, all_hw_submissions, total_enrollments):
    """Build per-homework stats plus the difficulty-ranked subset."""
    hw_submissions_by_homework = _dashboard_homework_submissions_by_homework(
        all_hw_submissions
    )
    homework_stats = _dashboard_homework_stat_rows(
        homeworks,
        hw_submissions_by_homework,
        total_enrollments,
    )
    difficulty_stats = _dashboard_homework_difficulty_stats(homework_stats)
    return homework_stats, difficulty_stats


def _dashboard_avg_total_score(course):
    enrollments_with_scores = Enrollment.objects.filter(
        course=course, total_score__isnull=False
    ).values_list("total_score", flat=True)
    return (
        statistics.mean(enrollments_with_scores)
        if enrollments_with_scores
        else 0
    )


def _dashboard_homeworks(course):
    return (
        Homework.objects.filter(course=course)
        .order_by("id")
        .annotate(
            max_questions_score=Sum("question__scores_for_correct_answer")
        )
    )


def _dashboard_homework_submissions(course):
    return (
        Submission.objects
        .filter(homework__course=course)
        .select_related("homework")
        .values(
            "homework_id",
            "time_spent_lectures",
            "time_spent_homework",
            "questions_score",
            "total_score",
        )
    )


def _dashboard_graduates_count(course):
    return (
        Enrollment.objects
        .filter(
            course=course, certificate_url__isnull=False
        )
        .exclude(certificate_url="")
        .count()
    )


def _dashboard_context(course):
    total_enrollments = Enrollment.objects.filter(course=course).count()
    homework_stats, homework_difficulty_stats = _dashboard_homework_stats(
        _dashboard_homeworks(course),
        _dashboard_homework_submissions(course),
        total_enrollments,
    )

    return {
        "course": course,
        "total_enrollments": total_enrollments,
        "avg_total_score": round(_dashboard_avg_total_score(course), 1),
        "project_passing_score": course.project_passing_score,
        "graduates_count": _dashboard_graduates_count(course),
        "homework_stats": homework_stats,
        "homework_difficulty_stats": homework_difficulty_stats,
        **_dashboard_project_stats(course, total_enrollments),
    }


def dashboard_view(request, course_slug: str):
    course = get_object_or_404(Course, slug=course_slug)
    if not course.first_homework_scored:
        return redirect("course", course_slug=course.slug)

    return render(
        request,
        "courses/dashboard.html",
        _dashboard_context(course),
    )
