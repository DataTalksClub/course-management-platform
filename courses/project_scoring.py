import logging

from functools import partial
from time import time

from django.db import transaction
from django.utils import timezone

from course_management.observability import record_event
from course_management.datamailer.sync.memberships import (
    sync_project_passed_outcome_to_datamailer,
    sync_project_submission_to_datamailer,
)

from courses.models.project import (
    Project,
    ProjectSubmission,
    PeerReview,
    ProjectState,
    ProjectEvaluationScore,
)

from . import project_assignment
from .leaderboard import update_leaderboard
from .project_score_calculation import (
    calculate_project_scoring,
)


logger = logging.getLogger(__name__)


def _validate_project_scoreable(project: Project) -> str | None:
    """Return an error message if the project can't be scored, else None."""
    if project.points_to_pass == 0:
        return "Project has no points to pass. Update the course's `project_passing_score` field to greater than zero value"

    if project.state != ProjectState.PEER_REVIEWING.value:
        return "Project is not in 'PEER_REVIEWING' state"

    if project.peer_review_due_date > timezone.now():
        return "The peer review due date is in the future. Update the due date to score the project."

    return None


def _sync_scored_project_submission_to_datamailer(submission):
    sync_project_submission_to_datamailer(submission)
    sync_project_passed_outcome_to_datamailer(submission)


def _peer_reviews_for_project(project):
    return PeerReview.objects.filter(
        submission_under_evaluation__project=project,
    ).select_related(
        "submission_under_evaluation",
        "submission_under_evaluation__enrollment",
        "reviewer",
    )


def _bulk_update_project_submissions(submissions_to_update):
    logger.info(f"updating {len(submissions_to_update)} submissions...")
    ProjectSubmission.objects.bulk_update(
        submissions_to_update,
        [
            "project_score",
            "project_faq_score",
            "project_learning_in_public_score",
            "peer_review_score",
            "peer_review_learning_in_public_score",
            "total_score",
            "reviewed_enough_peers",
            "passed",
        ],
    )


def _sync_project_submissions_after_commit(submissions_to_update):
    for submission in submissions_to_update:
        callback = partial(
            _sync_scored_project_submission_to_datamailer,
            submission,
        )
        transaction.on_commit(callback)


def _replace_project_evaluation_scores(submission_ids, all_scores):
    ProjectEvaluationScore.objects.filter(
        submission_id__in=submission_ids
    ).delete()
    ProjectEvaluationScore.objects.bulk_create(all_scores)


def _complete_scored_project(
    project,
    calculation,
):
    _bulk_update_project_submissions(calculation.submissions_to_update)
    _sync_project_submissions_after_commit(calculation.submissions_to_update)
    submission_ids = calculation.submissions.keys()
    _replace_project_evaluation_scores(
        submission_ids,
        calculation.evaluation_scores,
    )

    project.state = ProjectState.COMPLETED.value
    project.save()

    update_leaderboard(project.course)


def _project_scoreable_peer_reviews(project):
    error = _validate_project_scoreable(project)
    if error is not None:
        return None, error

    peer_reviews = _peer_reviews_for_project(project)
    if peer_reviews.count() == 0:
        return None, "No peer reviews found for the project."

    return peer_reviews, None


def _score_project_with_reviews(project, peer_reviews):
    calculation = calculate_project_scoring(project, peer_reviews)
    passed_ratio = calculation.passed_count / len(calculation.submissions)

    _complete_scored_project(
        project,
        calculation,
    )

    success_message = (
        f"Project {project.id} scored and state updated to "
        f"'COMPLETED'. {calculation.passed_count} passed "
        f"({passed_ratio:.2f})."
    )
    return success_message


def score_project(
    project: Project,
) -> tuple[project_assignment.ProjectActionStatus, str]:
    with transaction.atomic():
        t0 = time()

        peer_reviews, error = _project_scoreable_peer_reviews(project)
        if error is not None:
            record_event(
                "project.scoring_failed",
                properties={
                    "course_slug": project.course.slug,
                    "project_slug": project.slug,
                    "project_id": project.id,
                    "reason": error,
                },
            )
            return (project_assignment.ProjectActionStatus.FAIL, error)

        success_message = _score_project_with_reviews(project, peer_reviews)

        t_end = time()

        logger.info(
            f"Project {project.id} scored in {t_end - t0:.2f} seconds."
        )
        submissions_count = project.projectsubmission_set.count()
        passed_count = project.projectsubmission_set.filter(
            passed=True,
        ).count()
        record_event(
            "project.scored",
            properties={
                "course_slug": project.course.slug,
                "project_slug": project.slug,
                "project_id": project.id,
                "submissions_count": submissions_count,
                "passed_count": passed_count,
                "duration_ms": int((t_end - t0) * 1000),
            },
        )

    return (project_assignment.ProjectActionStatus.OK, success_message)
