from dataclasses import dataclass

from django.db.models import Prefetch
from django.utils import timezone

from courses.models.course import Course, User
from courses.models.project import (
    PeerReview,
    PeerReviewState,
    Project,
    ProjectState,
    ProjectSubmission,
)


@dataclass(frozen=True)
class ProjectBadgeData:
    name: str
    css_class: str
    score: object = None


def get_projects_for_course(
    course: Course, user: User
) -> list[Project]:
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


def project_days_until(due_date) -> int:
    now = timezone.now()
    if due_date > now:
        return (due_date - now).days
    return 0


def base_project_badge(state):
    if state == ProjectState.CLOSED.value:
        return ProjectBadgeData("Closed", "bg-secondary")
    if state == ProjectState.COLLECTING_SUBMISSIONS.value:
        return ProjectBadgeData("Open", "bg-warning")
    return ProjectBadgeData("Not submitted", "bg-secondary")


def peer_review_project_badge(project, submission):
    completed_reviews = PeerReview.objects.filter(
        reviewer=submission,
        optional=False,
        state=PeerReviewState.SUBMITTED.value,
    )
    completed_reviews_count = completed_reviews.count()
    if completed_reviews_count >= project.number_of_peers_to_evaluate:
        return ProjectBadgeData("Review completed", "bg-success")

    return ProjectBadgeData("Review", "bg-danger")


def completed_project_badge(submission):
    score = submission.total_score
    if submission.passed:
        label = f"Passed ({score})"
        badge = ProjectBadgeData(label, "bg-success", score)
        return badge

    label = f"Failed ({score})"
    badge = ProjectBadgeData(label, "bg-secondary", score)
    return badge


def submitted_project_badge(project, submission):
    state = project.state
    if state == ProjectState.COLLECTING_SUBMISSIONS.value:
        return ProjectBadgeData("Submitted", "bg-info")
    if state == ProjectState.PEER_REVIEWING.value:
        return peer_review_project_badge(project, submission)
    if state == ProjectState.COMPLETED.value:
        return completed_project_badge(submission)
    return None


def update_project_with_additional_info(project: Project) -> None:
    project.days_until_submission_due = project_days_until(
        project.submission_due_date
    )
    project.days_until_pr_due = project_days_until(
        project.peer_review_due_date
    )

    project.submitted = False
    project.score = None
    badge = base_project_badge(project.state)
    project.badge_state_name = badge.name
    project.badge_css_class = badge.css_class

    if not project.submissions:
        return

    submission = project.submissions[0]
    project.submitted = True
    project.submitted_at = submission.submitted_at

    override = submitted_project_badge(project, submission)
    if override is not None:
        project.badge_state_name = override.name
        project.badge_css_class = override.css_class
        project.score = override.score
