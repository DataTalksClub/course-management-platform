from django.utils import timezone

from courses.models.course import Course
from courses.models.project import Project, ProjectState, ProjectSubmission


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


def add_course_homepage_info(
    course: Course,
    now,
    submitted_project_ids: set[int] | None = None,
) -> None:
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
    ) = current_assignment_info(course, now, submitted_project_ids)


def submitted_project_ids_for_user(courses, user) -> set[int] | None:
    """Projects the user submitted, or None when there is no user context."""
    if user is None or not user.is_authenticated:
        return None

    course_ids = [course.id for course in courses]

    project_ids = ProjectSubmission.objects.filter(
        student=user,
        project__course_id__in=course_ids,
    ).values_list("project_id", flat=True)
    return set(project_ids)


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


def current_assignment_info(
    course: Course,
    now,
    submitted_project_ids: set[int] | None = None,
) -> tuple[str, dict | None]:
    assignments = get_course_assignments(course, submitted_project_ids)

    if not assignments:
        return "Current assignment", None

    upcoming_assignments = []
    for assignment in assignments:
        if assignment["due_date"] >= now:
            upcoming_assignments.append(assignment)

    if upcoming_assignments:
        return "Next assignment", upcoming_assignments[0]

    return "Last assignment", assignments[-1]


def get_course_assignments(
    course: Course,
    submitted_project_ids: set[int] | None = None,
) -> list[dict]:
    assignments = []

    homeworks = course.homework_set.all()
    for homework in homeworks:
        homework_assignment = homework_assignment_record(homework)
        assignments.append(homework_assignment)

    projects = course.project_set.all()
    for project in projects:
        project_assignment = project_assignment_record(project)
        assignments.append(project_assignment)

        if show_peer_review_assignment(project, submitted_project_ids):
            peer_review_assignment = peer_review_assignment_record(project)
            assignments.append(peer_review_assignment)

    return sorted(assignments, key=course_assignment_sort_key)


def show_peer_review_assignment(
    project: Project,
    submitted_project_ids: set[int] | None,
) -> bool:
    """Peer review is only relevant once the student can actually do it."""
    review_visible_states = {
        ProjectState.PEER_REVIEWING.value,
        ProjectState.COMPLETED.value,
    }
    if project.state not in review_visible_states:
        return False

    if submitted_project_ids is None:
        return True

    return project.id in submitted_project_ids


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
