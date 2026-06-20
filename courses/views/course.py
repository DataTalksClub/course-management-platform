import logging
import statistics

from collections import defaultdict
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
    for part in reversed(course.title.split()):
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

    for homework in course.homework_set.all():
        assignments.append(
            {
                "type": "homework",
                "label": "Homework",
                "title": homework.title,
                "due_date": homework.due_date,
            }
        )

    for project in course.project_set.all():
        assignments.append(
            {
                "type": "project",
                "label": "Project",
                "title": project.title,
                "due_date": project.submission_due_date,
            }
        )
        assignments.append(
            {
                "type": "peer_review",
                "label": "Peer review",
                "title": project.title,
                "due_date": project.peer_review_due_date,
            }
        )

    return sorted(
        assignments,
        key=lambda assignment: (
            assignment["due_date"],
            ASSIGNMENT_TYPE_ORDER[assignment["type"]],
        ),
    )


def current_assignment_info(course: Course, now) -> tuple[str, dict | None]:
    assignments = get_course_assignments(course)

    if not assignments:
        return "Current assignment", None

    upcoming_assignments = [
        assignment for assignment in assignments
        if assignment["due_date"] >= now
    ]

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
    course_ids = [course.id for course in courses]
    campaigns = RegistrationCampaign.objects.filter(
        current_course_id__in=course_ids,
        is_active=True,
    ).order_by("id")
    campaign_by_course_id = {}
    for campaign in campaigns:
        campaign_by_course_id.setdefault(campaign.current_course_id, campaign)

    for course in courses:
        course.registration_campaign = campaign_by_course_id.get(course.id)


def mark_registered_courses(courses, user) -> None:
    if not user.is_authenticated:
        return

    campaign_ids = [
        course.registration_campaign.id
        for course in courses
        if getattr(course, "registration_campaign", None)
    ]
    registered_campaign_ids = set(
        CourseRegistration.objects.filter(
            campaign_id__in=campaign_ids,
            email_normalized=(user.email or "").strip().lower(),
        ).values_list("campaign_id", flat=True)
    )

    for course in courses:
        campaign = getattr(course, "registration_campaign", None)
        course.is_registered = (
            campaign is not None and campaign.id in registered_campaign_ids
        )


def mark_enrolled_courses(courses, user) -> None:
    if not user.is_authenticated:
        return

    course_ids = [course.id for course in courses]
    enrolled_course_ids = set(
        Enrollment.objects.filter(
            student=user,
            course_id__in=course_ids,
        ).values_list("course_id", flat=True)
    )

    for course in courses:
        course.is_enrolled = course.id in enrolled_course_ids


def course_list(request):
    now = timezone.now()
    courses = (
        Course.objects.filter(visible=True)
        .annotate(
            homework_count=Count("homework", distinct=True),
            project_count=Count("project", distinct=True),
            learner_count=Count("enrollment", distinct=True),
        )
        .prefetch_related("homework_set", "project_set")
        .order_by("-id")
    )

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

    mark_enrolled_courses(courses, request.user)
    attach_registration_campaigns(courses)
    mark_registered_courses(courses, request.user)

    featured_course = None
    for course in active_courses:
        if not course.title.lower().startswith("fake"):
            featured_course = course
            break

    if featured_course is None and active_courses:
        featured_course = active_courses[0]

    other_active_courses = [
        course for course in active_courses if course != featured_course
    ]

    archive_years = sorted(
        archive_courses_by_year.keys(),
        key=lambda year: (year == "Archive", year),
        reverse=True,
    )
    if "Archive" in archive_years:
        archive_years.remove("Archive")
        archive_years.append("Archive")

    archive_groups = [
        {
            "year": year,
            "courses": archive_courses_by_year[year],
        }
        for year in archive_years
    ]

    context = {
        "active_courses": active_courses,
        "archive_groups": archive_groups,
        "featured_course": featured_course,
        "finished_courses": finished_courses,
        "other_active_courses": other_active_courses,
        "home_stats": {
            "active_courses": len(active_courses),
            "archive_courses": len(finished_courses),
            "homeworks": sum(course.homework_count for course in courses),
            "projects": sum(course.project_count for course in courses),
        },
    }

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


def _submitted_project_badge(project, submission):
    """Badge override (name, css, score) once a project has a submission.

    Returns None for states that keep the base badge (e.g. still CLOSED).
    """
    state = project.state
    if state == ProjectState.COLLECTING_SUBMISSIONS.value:
        return "Submitted", "bg-info", None

    if state == ProjectState.PEER_REVIEWING.value:
        # Real-time feedback during peer review: count submitted mandatory reviews.
        completed_reviews_count = PeerReview.objects.filter(
            reviewer=submission,
            optional=False,
            state=PeerReviewState.SUBMITTED.value,
        ).count()
        if completed_reviews_count >= project.number_of_peers_to_evaluate:
            return "Review completed", "bg-success", None
        return "Review", "bg-danger", None

    if state == ProjectState.COMPLETED.value:
        score = submission.total_score
        if submission.passed:
            return f"Passed ({score})", "bg-success", score
        return f"Failed ({score})", "bg-secondary", score

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


def course_view(request: HttpRequest, course_slug: str) -> HttpResponse:
    course = get_object_or_404(Course, slug=course_slug)
    add_course_homepage_info(course, timezone.now())

    user = request.user
    homeworks = get_homeworks_for_course(course, user)
    projects = get_projects_for_course(course, user)
    registration_campaign = (
        RegistrationCampaign.objects.filter(
            current_course=course,
            is_active=True,
        )
        .order_by("id")
        .first()
    )

    if (
        registration_campaign
        and not homeworks
        and not projects
        and not user.is_staff
    ):
        return redirect(
            "registration_campaign",
            campaign_slug=registration_campaign.slug,
        )

    has_completed_projects = False
    for project in projects:
        if project.state == ProjectState.COMPLETED.value:
            has_completed_projects = True

    total_score = None
    certificate_url = None
    has_enrollment = False
    has_registration = False
    if user.is_authenticated:
        try:
            enrollment = Enrollment.objects.get(
                student=user,
                course=course,
            )
            has_enrollment = True
            total_score = enrollment.total_score
            certificate_url = enrollment.certificate_url
        except Enrollment.DoesNotExist:
            pass
        if registration_campaign:
            has_registration = CourseRegistration.objects.filter(
                campaign=registration_campaign,
                email_normalized=(user.email or "").strip().lower(),
            ).exists()

    context = {
        "course": course,
        "homeworks": homeworks,
        "projects": projects,
        "has_completed_projects": has_completed_projects,
        "is_authenticated": user.is_authenticated,
        "has_enrollment": has_enrollment,
        "total_score": total_score,
        "certificate_url": certificate_url,
        "registration_campaign": registration_campaign,
        "has_registration": has_registration,
    }

    return render(request, "courses/course.html", context)


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


def course_calendar_view(
    request: HttpRequest,
    course_slug: str,
) -> HttpResponse:
    course = get_object_or_404(Course, slug=course_slug, visible=True)
    dtstamp = timezone.now()
    events = []

    homeworks = Homework.objects.filter(course=course).order_by("due_date")
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
        events.extend(
            calendar_event(
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
        )

    projects = Project.objects.filter(course=course).order_by(
        "submission_due_date",
        "peer_review_due_date",
    )
    for project in projects:
        project_url = request.build_absolute_uri(
            reverse(
                "project",
                kwargs={
                    "course_slug": course.slug,
                    "project_slug": project.slug,
                },
            )
        )
        events.extend(
            calendar_event(
                uid=f"project-{project.id}-submission@courses.datatalks.club",
                summary=f"{course.title}: {project.title} submission deadline",
                start=project.submission_due_date,
                url=project_url,
                description=(
                    f"Project submission deadline for {project.title}. "
                    f"Open the project: {project_url}"
                ),
                dtstamp=dtstamp,
            )
        )
        events.extend(
            calendar_event(
                uid=f"project-{project.id}-peer-review@courses.datatalks.club",
                summary=f"{course.title}: {project.title} peer review deadline",
                start=project.peer_review_due_date,
                url=project_url,
                description=(
                    f"Project peer review deadline for {project.title}. "
                    f"Open the project: {project_url}"
                ),
                dtstamp=dtstamp,
            )
        )

    calendar_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//DataTalks.Club//Course Management Platform//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escape_ics_text(course.title)} deadlines",
        *events,
        "END:VCALENDAR",
    ]

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


def leaderboard_view(request, course_slug: str):
    course = get_object_or_404(Course, slug=course_slug)

    user = request.user
    current_student_enrollment = None
    current_student_enrollment_id = None

    if user.is_authenticated:
        try:
            current_student_enrollment = Enrollment.objects.get(
                student=user,
                course=course,
            )
            current_student_enrollment_id = current_student_enrollment.id
        except Enrollment.DoesNotExist:
            pass

    cache_key = f"leaderboard:{course.id}"

    def build_leaderboard_data():
        logger.info(f"Cache miss for leaderboard of course {course.slug}")
        completed_project_submissions = Prefetch(
            "projectsubmission_set",
            queryset=ProjectSubmission.objects.filter(
                project__state=ProjectState.COMPLETED.value,
                volunteer_review_only=False,
            )
            .select_related("project")
            .order_by("project__id"),
            to_attr="completed_project_submissions",
        )
        enrollments = list(
            Enrollment.objects.filter(
                course=course,
                display_on_leaderboard=True,
            )
            .select_related('student')
            .prefetch_related(completed_project_submissions)
            .order_by(
                Coalesce("position_on_leaderboard", Value(999999)),
                "id",
            )
        )
        # Store as list of dictionaries to avoid stale model instances
        enrollments_data = [
            {
                'id': e.id,
                'display_name': e.display_name,
                'total_score': e.total_score,
                'position_on_leaderboard': e.position_on_leaderboard,
                'passed_projects': [
                    {
                        "title": sub.project.title,
                        "slug": sub.project.slug,
                        "attempt": index,
                        "medal_index": ((index - 1) % 5) + 1,
                    }
                    for index, sub in enumerate(
                        e.completed_project_submissions,
                        1,
                    )
                    if sub.passed
                ],
            }
            for e in enrollments
        ]
        cache.set(cache_key, enrollments_data, 3600)
        return enrollments_data

    # Try to get enrollments from cache. If the current student enrolled after
    # the cache was built, refresh so the jump link points to a rendered row.
    enrollments_data = cache.get(cache_key)

    if enrollments_data is None:
        enrollments_data = build_leaderboard_data()
    else:
        logger.info(f"Cache hit for leaderboard of course {course.slug}")
        if (
            current_student_enrollment_id is not None
            and current_student_enrollment.display_on_leaderboard
            and not any(
                enrollment["id"] == current_student_enrollment_id
                for enrollment in enrollments_data
            )
        ):
            enrollments_data = build_leaderboard_data()

    paginator = Paginator(enrollments_data, LEADERBOARD_PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get("page"))
    enrollments_page = page_obj.object_list

    current_student_page_number = None
    if (
        current_student_enrollment_id is not None
        and current_student_enrollment.display_on_leaderboard
    ):
        for index, enrollment in enumerate(enrollments_data):
            if enrollment["id"] == current_student_enrollment_id:
                current_student_page_number = (
                    index // LEADERBOARD_PAGE_SIZE
                ) + 1
                break

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

    state_order = Case(
        When(homework__state=HomeworkState.SCORED.value, then=Value(0)),
        When(homework__state=HomeworkState.OPEN.value, then=Value(1)),
        When(homework__state=HomeworkState.CLOSED.value, then=Value(2)),
        default=Value(3),
        output_field=IntegerField(),
    )

    # Update the queryset to use the custom sorting order
    homework_submissions = Submission.objects.filter(
        enrollment=enrollment
    ).order_by(state_order, "homework__id")

    project_submissions = ProjectSubmission.objects.filter(
        enrollment=enrollment,
        volunteer_review_only=False,
    ).order_by("project__id")

    is_own_record = (
        request.user.is_authenticated
        and request.user.id == enrollment.student_id
    )
    public_profile = (
        enrollment.student if enrollment.display_public_profile else None
    )

    context = {
        "enrollment": enrollment,
        "public_profile": public_profile,
        "show_public_profile_settings_link": (
            is_own_record and public_profile is None
        ),
        "submissions": homework_submissions,
        "project_submissions": project_submissions,
    }

    return render(
        request, "courses/leaderboard_score_breakdown.html", context
    )


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


@login_required
def enrollment_view(request, course_slug):
    course = get_object_or_404(Course, slug=course_slug)

    enrollment, _ = Enrollment.objects.get_or_create(
        student=request.user,
        course=course,
    )

    if request.method == "POST":
        form = EnrollmentForm(
            request.POST,
            instance=enrollment,
            user=request.user,
        )
        if form.is_valid():
            previous_display_on_leaderboard = (
                enrollment.display_on_leaderboard
            )
            form.save()
            if (
                previous_display_on_leaderboard
                != form.instance.display_on_leaderboard
            ):
                invalidate_leaderboard_cache(course.id)
            return redirect("course", course_slug=course_slug)
        else:
            context = {
                "form": form,
                "course": course,
                "enrollment": enrollment,
            }
            return render(request, "courses/enrollment.html", context)

    form = EnrollmentForm(instance=enrollment, user=request.user)

    context = {
        "form": form,
        "course": course,
        "enrollment": enrollment,
    }

    return render(request, "courses/enrollment.html", context)


def list_all_project_submissions_view(request, course_slug: str):
    course = get_object_or_404(Course, slug=course_slug)

    projects = (
        Project.objects.filter(course=course)
        .annotate(
            submissions_count=Count(
                "projectsubmission",
                filter=Q(projectsubmission__volunteer_review_only=False),
            )
        )
        .order_by("id")
    )

    submissions = (
        ProjectSubmission.objects.filter(
            project__course=course,
            volunteer_review_only=False,
        )
        .select_related("project", "enrollment")
        .annotate(
            vote_count=Count("votes"),
            display_score=Case(
                When(
                    project__state=ProjectState.COMPLETED.value,
                    then="project_score",
                ),
                default=Value(-1),
                output_field=IntegerField(),
            )
        )
        .order_by("-vote_count", "-display_score", "project__id", "submitted_at")
    )

    submissions_page = Paginator(
        submissions, PROJECT_SUBMISSIONS_PAGE_SIZE
    ).get_page(request.GET.get("page"))

    context = {
        "course": course,
        "projects": projects,
        "submissions": submissions_page.object_list,
        "submissions_page": submissions_page,
        "page_range": submissions_page.paginator.get_elided_page_range(
            submissions_page.number
        ),
        "is_authenticated": request.user.is_authenticated,
    }

    return render(request, "projects/list_all.html", context)


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
    project_submissions = list(
        ProjectSubmission.objects.filter(project__course=course)
        .select_related("project", "enrollment")
        .values("enrollment_id", "time_spent", "total_score", "passed")
    )

    # Project completion: share of enrolled students who submitted at least one
    # project. Counting distinct enrollments keeps the rate <= 100% when a
    # course has multiple projects (a student who submits several must not be
    # counted more than once).
    enrollments_with_submission = {
        s["enrollment_id"] for s in project_submissions
    }
    completion_rate = (
        len(enrollments_with_submission) / total_enrollments * 100
        if total_enrollments > 0
        else 0
    )

    time_spent = [
        s["time_spent"]
        for s in project_submissions
        if s["time_spent"] is not None
    ]
    scores = [
        s["total_score"]
        for s in project_submissions
        if s["total_score"] is not None
    ]
    pass_count = sum(1 for s in project_submissions if s["passed"])
    fail_count = sum(1 for s in project_submissions if not s["passed"])

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


def _dashboard_homework_stat(homework, hw_submissions, total_enrollments):
    """Per-homework statistics row for the dashboard."""
    hw_time_lecture = [
        s["time_spent_lectures"]
        for s in hw_submissions
        if s["time_spent_lectures"] is not None
    ]
    hw_time_homework = [
        s["time_spent_homework"]
        for s in hw_submissions
        if s["time_spent_homework"] is not None
    ]
    hw_scores = [
        s["total_score"]
        for s in hw_submissions
        if s["total_score"] is not None
    ]
    hw_questions_scores = [
        s["questions_score"]
        for s in hw_submissions
        if s["questions_score"] is not None
    ]
    hw_time_total = [
        s["time_spent_lectures"] + s["time_spent_homework"]
        for s in hw_submissions
        if s["time_spent_lectures"] is not None
        and s["time_spent_homework"] is not None
    ]

    lecture_q25, lecture_median, lecture_q75 = _safe_quartiles(
        hw_time_lecture
    )
    homework_q25, homework_median, homework_q75 = _safe_quartiles(
        hw_time_homework
    )
    total_q25, total_median, total_q75 = _safe_quartiles(hw_time_total)
    score_q25, score_median, score_q75 = _safe_quartiles(hw_scores)

    # Difficulty is judged on the questions score (excluding bonus points such
    # as FAQ / learning-in-public) normalized by the max achievable questions
    # score, so homeworks with different question counts are comparable.
    # Lower ratio == harder.
    _, questions_score_median, _ = _safe_quartiles(hw_questions_scores)
    max_questions_score = homework.max_questions_score
    score_ratio = (
        questions_score_median / max_questions_score
        if questions_score_median is not None and max_questions_score
        else None
    )

    return {
        "homework": homework,
        "submissions_count": len(hw_submissions),
        "completion_rate": round(
            len(hw_submissions) / total_enrollments * 100, 1
        )
        if total_enrollments > 0
        else 0.0,
        "time_lecture_q25": lecture_q25,
        "time_lecture_median": lecture_median,
        "time_lecture_q75": lecture_q75,
        "time_lecture_median_formatted": _format_median(lecture_median),
        "time_homework_q25": homework_q25,
        "time_homework_median": homework_median,
        "time_homework_q75": homework_q75,
        "time_homework_median_formatted": _format_median(homework_median),
        "time_total_q25": total_q25,
        "time_total_median": total_median,
        "time_total_q75": total_q75,
        "time_total_median_formatted": _format_median(total_median),
        "score_q25": score_q25,
        "score_median": score_median,
        "score_q75": score_q75,
        "questions_score_median": questions_score_median,
        "max_questions_score": max_questions_score,
        "score_ratio": score_ratio,
        "score_ratio_pct": round(score_ratio * 100, 1)
        if score_ratio is not None
        else None,
    }


def _dashboard_homework_stats(homeworks, all_hw_submissions, total_enrollments):
    """Build per-homework stats plus the difficulty-ranked subset."""
    hw_submissions_by_homework = defaultdict(list)
    for submission in all_hw_submissions:
        hw_submissions_by_homework[submission["homework_id"]].append(
            submission
        )

    homework_stats = [
        _dashboard_homework_stat(
            homework,
            hw_submissions_by_homework.get(homework.id, []),
            total_enrollments,
        )
        for homework in homeworks
    ]

    difficulty_stats = [
        hw_stat
        for hw_stat in homework_stats
        if hw_stat["score_ratio"] is not None
    ]
    difficulty_stats.sort(
        key=lambda hw_stat: (
            hw_stat["score_ratio"],
            -hw_stat["submissions_count"],
            hw_stat["homework"].title,
        )
    )
    for rank, hw_stat in enumerate(difficulty_stats, start=1):
        hw_stat["difficulty_rank"] = rank

    return homework_stats, difficulty_stats


def dashboard_view(request, course_slug: str):
    course = get_object_or_404(Course, slug=course_slug)
    if not course.first_homework_scored:
        return redirect("course", course_slug=course.slug)

    total_enrollments = Enrollment.objects.filter(course=course).count()

    project_stats = _dashboard_project_stats(course, total_enrollments)

    # Average of stored per-enrollment total scores.
    enrollments_with_scores = Enrollment.objects.filter(
        course=course, total_score__isnull=False
    ).values_list("total_score", flat=True)
    avg_total_score = (
        statistics.mean(enrollments_with_scores)
        if enrollments_with_scores
        else 0
    )

    # The max achievable questions score (sum of points across the homework's
    # questions) lets us normalize difficulty: a homework with fewer questions
    # naturally has a lower median score without being harder.
    homeworks = (
        Homework.objects.filter(course=course)
        .order_by("id")
        .annotate(
            max_questions_score=Sum("question__scores_for_correct_answer")
        )
    )
    all_hw_submissions = (
        Submission.objects.filter(homework__course=course)
        .select_related("homework")
        .values(
            "homework_id",
            "time_spent_lectures",
            "time_spent_homework",
            "questions_score",
            "total_score",
        )
    )
    homework_stats, homework_difficulty_stats = _dashboard_homework_stats(
        homeworks, all_hw_submissions, total_enrollments
    )

    # Graduates: enrollments with a (non-empty) certificate.
    graduates_count = (
        Enrollment.objects.filter(
            course=course, certificate_url__isnull=False
        )
        .exclude(certificate_url="")
        .count()
    )

    context = {
        "course": course,
        "total_enrollments": total_enrollments,
        "avg_total_score": round(avg_total_score, 1),
        "project_passing_score": course.project_passing_score,
        "graduates_count": graduates_count,
        "homework_stats": homework_stats,
        "homework_difficulty_stats": homework_difficulty_stats,
        **project_stats,
    }

    return render(request, "courses/dashboard.html", context)
