import logging
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from time import time

from django.db import transaction
from django.utils import timezone

from course_management.deadlines import ceil_to_next_hour

from courses.models.project import (
    PeerReview,
    Project,
    ProjectState,
    ProjectSubmission,
)
from courses.project_assignment_selection import (
    select_random_assignment as _select_random_assignment,
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
    assignments = _select_random_assignment(
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
