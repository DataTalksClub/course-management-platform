from collections import defaultdict
from dataclasses import dataclass

from django.db.models import Count
from django.shortcuts import render
from django.utils import timezone

from courses.models import (
    Course,
    CourseRegistration,
    Enrollment,
    RegistrationCampaign,
)


@dataclass(frozen=True)
class CourseListCourses:
    courses: list
    active_courses: list
    finished_courses: list
    archive_courses_by_year: dict


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


def registration_campaign_ids(courses):
    campaign_ids = []
    for course in courses:
        registration_campaign = getattr(course, "registration_campaign", None)
        if registration_campaign:
            campaign_ids.append(registration_campaign.id)
    return campaign_ids


def normalized_user_email(user) -> str:
    email = user.email or ""
    stripped_email = email.strip()
    return stripped_email.lower()


def registered_campaign_ids(campaign_ids, user):
    email_normalized = normalized_user_email(user)
    registration_ids = CourseRegistration.objects.filter(
        campaign_id__in=campaign_ids,
        email_normalized=email_normalized,
    ).values_list("campaign_id", flat=True)
    return set(registration_ids)


def mark_registered_course(course, registered_campaign_ids) -> None:
    campaign = getattr(course, "registration_campaign", None)
    course.is_registered = (
        campaign is not None and campaign.id in registered_campaign_ids
    )


def mark_registered_courses(courses, user) -> None:
    if not user.is_authenticated:
        return

    campaign_ids = registration_campaign_ids(courses)
    registered_ids = registered_campaign_ids(campaign_ids, user)
    for course in courses:
        mark_registered_course(course, registered_ids)


def mark_enrolled_courses(courses, user) -> None:
    if not user.is_authenticated:
        return

    course_ids = []
    for course in courses:
        course_ids.append(course.id)
    enrolled_ids = Enrollment.objects.filter(
        student=user,
        course_id__in=course_ids,
    ).values_list("course_id", flat=True)
    enrolled_course_ids = set(enrolled_ids)

    for course in courses:
        course.is_enrolled = course.id in enrolled_course_ids


def visible_course_list_queryset():
    courses = Course.objects.filter(visible=True)
    homework_count = Count("homework", distinct=True)
    project_count = Count("project", distinct=True)
    learner_count = Count("enrollment", distinct=True)
    courses = courses.annotate(
        homework_count=homework_count,
        project_count=project_count,
        learner_count=learner_count,
    )
    courses = courses.prefetch_related("homework_set", "project_set")
    return courses.order_by("-id")


def split_courses_by_status(courses, now):
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
        courses=courses,
        active_courses=active_courses,
        finished_courses=finished_courses,
        archive_courses_by_year=archive_courses_by_year,
    )


def featured_course(active_courses):
    for course in active_courses:
        title = course.title.lower()
        if not title.startswith("fake"):
            return course

    if active_courses:
        return active_courses[0]

    return None


def archive_year_sort_key(year):
    return (year == "Archive", year)


def course_archive_groups(archive_courses_by_year):
    archive_year_keys = archive_courses_by_year.keys()
    archive_years = sorted(
        archive_year_keys,
        key=archive_year_sort_key,
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


def course_home_stats(courses, active_courses, finished_courses):
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


def other_active_courses(active_courses, featured_course):
    other_courses = []
    for course in active_courses:
        if course != featured_course:
            other_courses.append(course)
    return other_courses


def prepare_course_list_courses(user):
    visible_courses = visible_course_list_queryset()
    courses = list(visible_courses)
    now = timezone.now()
    course_groups = split_courses_by_status(courses, now)

    mark_enrolled_courses(course_groups.courses, user)
    attach_registration_campaigns(course_groups.courses)
    mark_registered_courses(course_groups.courses, user)

    return course_groups


def course_list_context(user):
    course_groups = prepare_course_list_courses(user)
    selected_featured_course = featured_course(course_groups.active_courses)
    archive_groups = course_archive_groups(
        course_groups.archive_courses_by_year
    )
    secondary_active_courses = other_active_courses(
        course_groups.active_courses,
        selected_featured_course,
    )
    home_stats = course_home_stats(
        course_groups.courses,
        course_groups.active_courses,
        course_groups.finished_courses,
    )

    return {
        "active_courses": course_groups.active_courses,
        "archive_groups": archive_groups,
        "featured_course": selected_featured_course,
        "finished_courses": course_groups.finished_courses,
        "other_active_courses": secondary_active_courses,
        "home_stats": home_stats,
    }


def course_list(request):
    context = course_list_context(request.user)
    return render(
        request,
        "courses/course_list.html",
        context,
    )
