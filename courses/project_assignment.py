import logging
import random
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from time import time

from django.db import transaction
from django.utils import timezone

from course_management.deadlines import ceil_to_next_hour

from courses.models.project import (
    PeerReview,
    PeerReviewState,
    Project,
    ProjectState,
    ProjectSubmission,
)


logger = logging.getLogger(__name__)

# How long the peer-review window stays open after submissions close.
PEER_REVIEW_WINDOW = timedelta(days=7)


class ProjectActionStatus(Enum):
    OK = "OK"
    FAIL = "Warning"


@dataclass(frozen=True)
class PeerReviewAssignmentData:
    project: Project
    submissions: object
    num_evaluations: int
    started_at: float


def select_random_assignment(
    submissions: list[ProjectSubmission],
    num_projects_to_review: int,
    seed: int = 1,
) -> list[PeerReview]:
    num_submissions = len(submissions)
    _validate_peer_review_assignment_size(
        num_submissions,
        num_projects_to_review,
    )
    random.seed(seed)

    submissions_list = list(submissions)
    projects_pool = _review_slot_project_pools(
        num_submissions, num_projects_to_review
    )

    all_assignments = []
    for reviewer_idx, reviewer_submission in enumerate(submissions_list):
        assignments = _select_reviewer_assignments(
            reviewer_idx,
            reviewer_submission,
            submissions_list,
            projects_pool,
        )
        all_assignments.extend(assignments)

    return all_assignments


def _validate_peer_review_assignment_size(
    num_submissions: int,
    num_projects_to_review: int,
) -> None:
    if num_submissions > num_projects_to_review:
        return

    raise ValueError(
        "The number of projects to review should be greater than the number of submissions. "
        + f"Number of projects to review: {num_projects_to_review}, Number of submissions: {num_submissions}"
    )


def _review_slot_project_pools(
    num_submissions: int,
    num_projects_to_review: int,
) -> list[list[int]]:
    project_pools = []
    for _ in range(num_projects_to_review):
        project_pool = list(range(num_submissions))
        project_pools.append(project_pool)
    return project_pools


def _select_reviewer_assignments(
    reviewer_idx: int,
    reviewer_submission: ProjectSubmission,
    submissions: list[ProjectSubmission],
    projects_pool: list[list[int]],
) -> list[PeerReview]:
    selected = {reviewer_idx}
    assignments = []
    num_submissions = len(submissions)

    for projects in projects_pool:
        selected_project_idx = _select_project_for_review(
            projects,
            selected,
            num_submissions,
        )
        selected.add(selected_project_idx)
        _remove_project_from_slot_pool(selected_project_idx, projects)
        selected_project = submissions[selected_project_idx]
        assignment = _peer_review_assignment(
            reviewer_submission,
            selected_project,
        )
        assignments.append(assignment)

    return assignments


def _select_project_for_review(
    projects: list[int],
    selected: set[int],
    num_submissions: int,
) -> int:
    available = _available_review_projects(projects, selected)
    if not available:
        available = _fallback_review_projects(selected, num_submissions)
    return random.choice(available)


def _available_review_projects(
    projects: list[int],
    selected: set[int],
) -> list[int]:
    available_projects = []
    for project in projects:
        if project not in selected:
            available_projects.append(project)
    return available_projects


def _fallback_review_projects(
    selected: set[int],
    num_submissions: int,
) -> list[int]:
    fallback_projects = []
    for project in range(num_submissions):
        if project not in selected:
            fallback_projects.append(project)
    return fallback_projects


def _remove_project_from_slot_pool(
    project_idx: int,
    projects: list[int],
) -> None:
    if project_idx in projects:
        projects.remove(project_idx)


def _peer_review_assignment(
    reviewer_submission: ProjectSubmission,
    selected_project: ProjectSubmission,
) -> PeerReview:
    return PeerReview(
        submission_under_evaluation=selected_project,
        reviewer=reviewer_submission,
        state=PeerReviewState.TO_REVIEW.value,
        optional=False,
    )


def _assignment_precondition_failure(
    project: Project,
    submissions_count: int,
    num_evaluations: int,
) -> tuple[ProjectActionStatus, str] | None:
    if project.state != ProjectState.COLLECTING_SUBMISSIONS.value:
        return (
            ProjectActionStatus.FAIL,
            "Project is not in 'COLLECTING_SUBMISSIONS' state to assign peer reviews.",
        )

    if project.submission_due_date > timezone.now():
        return (
            ProjectActionStatus.FAIL,
            "The submission due date is in the future. Update the due date to assign peer reviews.",
        )

    if submissions_count <= num_evaluations:
        return (
            ProjectActionStatus.FAIL,
            f"Not enough submissions to assign {num_evaluations} peer reviews each.",
        )

    return None


def _open_peer_review_window(project: Project) -> None:
    # Closing submissions deterministically starts a fresh seven-day review window.
    review_window_end = timezone.now() + PEER_REVIEW_WINDOW
    project.peer_review_due_date = ceil_to_next_hour(review_window_end)
    project.state = ProjectState.PEER_REVIEWING.value
    project.save()


def _peer_review_assignment_data(project: Project) -> PeerReviewAssignmentData:
    submissions = ProjectSubmission.objects.filter(
        project=project
    ).select_related("enrollment")
    started_at = time()
    return PeerReviewAssignmentData(
        project=project,
        submissions=submissions,
        num_evaluations=project.number_of_peers_to_evaluate,
        started_at=started_at,
    )


def _assign_peer_reviews(data: PeerReviewAssignmentData) -> None:
    assignments = select_random_assignment(
        data.submissions,
        data.num_evaluations,
        seed=42,
    )
    PeerReview.objects.bulk_create(assignments)
    _open_peer_review_window(data.project)


def _log_peer_review_assignment(data: PeerReviewAssignmentData) -> None:
    duration = time() - data.started_at
    logger.info(
        f"Peer reviews assigned for project {data.project.id} in {duration:.2f} seconds."
    )


def assign_peer_reviews_for_project(
    project: Project,
) -> tuple[ProjectActionStatus, str]:
    with transaction.atomic():
        data = _peer_review_assignment_data(project)
        submissions_count = data.submissions.count()
        failure = _assignment_precondition_failure(
            project,
            submissions_count,
            data.num_evaluations,
        )
        if failure is not None:
            return failure

        _assign_peer_reviews(data)
        _log_peer_review_assignment(data)

    return (
        ProjectActionStatus.OK,
        f"Peer reviews assigned for project {project.id} and state updated to 'PEER_REVIEWING'.",
    )
