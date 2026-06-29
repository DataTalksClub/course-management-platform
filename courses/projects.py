import random
import logging

from time import time
from datetime import timedelta
from enum import Enum
from collections import defaultdict

from typing import List, Tuple, Iterable

import math
import statistics

from django.db import transaction
from django.utils import timezone

from course_management.datamailer import (
    sync_project_passed_outcome_to_datamailer,
    sync_project_submission_to_datamailer,
)
from course_management.deadlines import ceil_to_next_hour

from courses.models import (
    Project,
    ProjectSubmission,
    PeerReview,
    ProjectState,
    PeerReviewState,
    ProjectEvaluationScore,
    CriteriaResponse,
    ReviewCriteria,
)

from .scoring import update_leaderboard


logger = logging.getLogger(__name__)

# How long the peer-review window stays open after submissions close.
PEER_REVIEW_WINDOW = timedelta(days=7)


class ProjectActionStatus(Enum):
    OK = "OK"
    FAIL = "Warning"


def select_random_assignment(
    submissions: list[ProjectSubmission],
    num_projects_to_review: int,
    seed: int = 1,
) -> list[PeerReview]:
    n = len(submissions)
    _validate_peer_review_assignment_size(n, num_projects_to_review)
    random.seed(seed)

    submissions_list = list(submissions)
    projects_pool = _review_slot_project_pools(
        n, num_projects_to_review
    )

    all_assignments = []
    for reviewer_idx, reviewer_submission in enumerate(
        submissions_list
    ):
        all_assignments.extend(
            _select_reviewer_assignments(
                reviewer_idx,
                reviewer_submission,
                submissions_list,
                projects_pool,
            )
        )

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
    return [
        list(range(num_submissions))
        for _ in range(num_projects_to_review)
    ]


def _select_reviewer_assignments(
    reviewer_idx: int,
    reviewer_submission: ProjectSubmission,
    submissions: list[ProjectSubmission],
    projects_pool: list[list[int]],
) -> list[PeerReview]:
    selected = {reviewer_idx}
    assignments = []

    for projects in projects_pool:
        selected_project_idx = _select_project_for_review(
            projects,
            selected,
            len(submissions),
        )
        selected.add(selected_project_idx)
        _remove_project_from_slot_pool(selected_project_idx, projects)
        assignments.append(
            _peer_review_assignment(
                reviewer_submission,
                submissions[selected_project_idx],
            )
        )

    return assignments


def _select_project_for_review(
    projects: list[int],
    selected: set[int],
    num_submissions: int,
) -> int:
    available = [
        project for project in projects if project not in selected
    ]
    if not available:
        available = [
            project
            for project in range(num_submissions)
            if project not in selected
        ]

    return random.choice(available)


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
    project.peer_review_due_date = ceil_to_next_hour(
        timezone.now() + PEER_REVIEW_WINDOW
    )
    project.state = ProjectState.PEER_REVIEWING.value
    project.save()


def assign_peer_reviews_for_project(
    project: Project,
) -> tuple[ProjectActionStatus, str]:
    with transaction.atomic():
        t0 = time()
        submissions = ProjectSubmission.objects.filter(
            project=project
        ).select_related("enrollment")
        num_evaluations = project.number_of_peers_to_evaluate
        failure = _assignment_precondition_failure(
            project, submissions.count(), num_evaluations
        )
        if failure is not None:
            return failure

        assignments = select_random_assignment(
            submissions, num_evaluations, seed=42
        )
        PeerReview.objects.bulk_create(assignments)
        # Open the peer-review window for 7 days from now, rounded up to the
        # next whole hour. This always overwrites any previously set deadline
        # so closing submissions deterministically (re)starts the review clock.
        _open_peer_review_window(project)
        t_end = time()
        logger.info(
            f"Peer reviews assigned for project {project.id} in {t_end - t0:.2f} seconds."
        )

    return (
        ProjectActionStatus.OK,
        f"Peer reviews assigned for project {project.id} and state updated to 'PEER_REVIEWING'.",
    )


def calculate_median_score(
    submission: ProjectSubmission,
    evaluation_criteria: List[ReviewCriteria],
) -> Tuple[int, List[ProjectEvaluationScore]]:
    scores = []
    total_score = 0

    for criteria in evaluation_criteria:
        median_score = criteria.median_score()
        score = ProjectEvaluationScore(
            submission=submission,
            review_criteria=criteria,
            score=median_score,
        )

        scores.append(score)
        total_score += median_score

    return total_score, scores


def calculate_project_score(
    submission: ProjectSubmission,
    evaluation_criteria: Iterable[ReviewCriteria],
    reviews: List[PeerReview],
) -> Tuple[int, List[ProjectEvaluationScore]]:
    if len(reviews) == 0:
        logger.info(f"No reviews found for submission {submission.id}")
        return calculate_median_score(submission, evaluation_criteria)

    new_evaluations: List[ProjectEvaluationScore] = []

    project_score = 0
    responses_by_criteria = responses_grouped_by_criteria(reviews)

    for responses in responses_by_criteria.values():
        criteria_score, evaluation = score_project_criteria(
            submission, responses
        )
        new_evaluations.append(evaluation)
        project_score += criteria_score

    return project_score, new_evaluations


def responses_grouped_by_criteria(reviews: List[PeerReview]):
    responses_by_criteria = defaultdict(list)
    for review in reviews:
        for response in review.responses:
            responses_by_criteria[response.criteria_id].append(response)
    return responses_by_criteria


def score_project_criteria(
    submission: ProjectSubmission,
    responses: list[CriteriaResponse],
) -> tuple[int, ProjectEvaluationScore]:
    criteria = responses[0].criteria
    criteria_score = math.ceil(
        statistics.median(response.get_score() for response in responses)
    )
    return criteria_score, ProjectEvaluationScore(
        submission=submission,
        review_criteria=criteria,
        score=criteria_score,
    )


def _validate_project_scoreable(project: Project) -> str | None:
    """Return an error message if the project can't be scored, else None."""
    if project.points_to_pass == 0:
        return "Project has no points to pass. Update the course's `project_passing_score` field to greater than zero value"

    if project.state != ProjectState.PEER_REVIEWING.value:
        return "Project is not in 'PEER_REVIEWING' state"

    if project.peer_review_due_date > timezone.now():
        return "The peer review due date is in the future. Update the due date to score the project."

    return None


def _group_peer_reviews(peer_reviews):
    """Group submitted peer reviews by submission and by reviewer.

    Also attaches each submitted review's criteria responses as
    ``review.responses``. Returns (submissions, reviews_by_submission,
    reviews_by_reviewer).
    """
    criteria_responses = CriteriaResponse.objects.filter(
        review__in=peer_reviews
    ).select_related("criteria")

    responses_by_review = defaultdict(list)
    for response in criteria_responses:
        responses_by_review[response.review_id].append(response)

    submissions = {}
    reviews_by_submission = {}
    reviews_by_reviewer = {}

    for review in peer_reviews:
        submission = review.submission_under_evaluation
        submissions[submission.id] = submission

        if submission.id not in reviews_by_submission:
            reviews_by_submission[submission.id] = []

        if review.reviewer.id not in reviews_by_reviewer:
            reviews_by_reviewer[review.reviewer.id] = []

        if review.state == PeerReviewState.SUBMITTED.value:
            reviews_by_submission[submission.id].append(review)
            reviews_by_reviewer[review.reviewer.id].append(review)
            review.responses = responses_by_review[review.id]

    return submissions, reviews_by_submission, reviews_by_reviewer


def _project_lip_score(submission, project) -> int:
    """Learning-in-public points for the submission's own links (capped)."""
    if submission.enrollment.disable_learning_in_public:
        return 0
    if not submission.learning_in_public_links:
        return 0
    return min(
        len(submission.learning_in_public_links),
        project.learning_in_public_cap_project,
    )


def _peer_review_lip_score(submission, project, reviewed) -> int:
    """Learning-in-public points earned across the reviews this student gave."""
    if submission.enrollment.disable_learning_in_public:
        return 0
    cap = project.learning_in_public_cap_review
    total = 0
    for review in reviewed:
        if not review.learning_in_public_links:
            continue
        total += min(len(review.learning_in_public_links), cap)
    return total


def _mandatory_reviews_count(reviewed) -> int:
    return sum(1 for review in reviewed if not review.optional)


def _project_faq_score(submission) -> int:
    if submission.faq_contribution_url and len(submission.faq_contribution_url) >= 5:
        return 1
    return 0


def _project_total_score(submission) -> int:
    return (
        submission.project_score
        + submission.project_faq_score
        + submission.project_learning_in_public_score
        + submission.peer_review_score
        + submission.peer_review_learning_in_public_score
    )


def _assign_peer_review_scores(submission, project, reviewed) -> int:
    mandatory_reviews_count = _mandatory_reviews_count(reviewed)
    submission.peer_review_score = (
        mandatory_reviews_count * project.points_for_peer_review
    )
    submission.peer_review_learning_in_public_score = (
        _peer_review_lip_score(submission, project, reviewed)
    )
    submission.reviewed_enough_peers = (
        mandatory_reviews_count >= project.number_of_peers_to_evaluate
    )
    return mandatory_reviews_count


def _score_submission(submission, project, reviews, reviewed, criteria):
    """Compute and assign every score component for a single submission.

    Mutates ``submission`` in place and returns the per-criteria
    ProjectEvaluationScore objects produced for it.
    """
    project_score, scores = calculate_project_score(
        submission=submission,
        evaluation_criteria=criteria,
        reviews=reviews,
    )
    submission.project_score = project_score

    _assign_peer_review_scores(submission, project, reviewed)
    submission.project_learning_in_public_score = _project_lip_score(
        submission, project
    )
    submission.project_faq_score = _project_faq_score(submission)
    submission.total_score = _project_total_score(submission)
    submission.passed = (
        submission.project_score >= project.points_to_pass
    ) and submission.reviewed_enough_peers

    return scores


def _sync_scored_project_submission_to_datamailer(submission):
    sync_project_submission_to_datamailer(submission)
    sync_project_passed_outcome_to_datamailer(submission)


def _peer_reviews_for_project(project):
    return PeerReview.objects.filter(
        submission_under_evaluation__project=project,
    ).select_related("submission_under_evaluation", "reviewer")


def _score_project_submissions(
    project,
    submissions,
    reviews_by_submission,
    reviews_by_reviewer,
    criteria,
):
    submissions_to_update = []
    all_scores = []
    passed = 0

    for submission_id, submission in submissions.items():
        reviews = reviews_by_submission[submission_id]
        reviewed = reviews_by_reviewer.get(submission_id) or []

        scores = _score_submission(
            submission, project, reviews, reviewed, criteria
        )
        all_scores.extend(scores)
        submissions_to_update.append(submission)

        if submission.passed:
            passed += 1

    return submissions_to_update, all_scores, passed


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
        transaction.on_commit(
            lambda submission=submission: (
                _sync_scored_project_submission_to_datamailer(
                    submission
                )
            )
        )


def _replace_project_evaluation_scores(submission_ids, all_scores):
    ProjectEvaluationScore.objects.filter(
        submission_id__in=submission_ids
    ).delete()
    ProjectEvaluationScore.objects.bulk_create(all_scores)


def _calculate_project_scoring(project, peer_reviews):
    submissions, reviews_by_submission, reviews_by_reviewer = (
        _group_peer_reviews(peer_reviews)
    )

    criteria = ReviewCriteria.objects.filter(
        course=project.course
    ).all()

    submissions_to_update, all_scores, passed = (
        _score_project_submissions(
            project,
            submissions,
            reviews_by_submission,
            reviews_by_reviewer,
            criteria,
        )
    )

    return submissions, submissions_to_update, all_scores, passed


def _complete_scored_project(
    project,
    submissions,
    submissions_to_update,
    all_scores,
):
    _bulk_update_project_submissions(submissions_to_update)
    _sync_project_submissions_after_commit(submissions_to_update)
    _replace_project_evaluation_scores(
        submissions.keys(),
        all_scores,
    )

    project.state = ProjectState.COMPLETED.value
    project.save()

    update_leaderboard(project.course)


def _project_score_success_message(project, passed, passed_ratio):
    return (
        f"Project {project.id} scored and state updated to "
        f"'COMPLETED'. {passed} passed ({passed_ratio:.2f})."
    )


def score_project(project: Project) -> tuple[ProjectActionStatus, str]:
    with transaction.atomic():
        t0 = time()

        error = _validate_project_scoreable(project)
        if error is not None:
            return (ProjectActionStatus.FAIL, error)

        peer_reviews = _peer_reviews_for_project(project)
        if peer_reviews.count() == 0:
            return (
                ProjectActionStatus.FAIL,
                "No peer reviews found for the project.",
            )

        submissions, submissions_to_update, all_scores, passed = (
            _calculate_project_scoring(project, peer_reviews)
        )
        passed_ratio = passed / len(submissions)

        _complete_scored_project(
            project,
            submissions,
            submissions_to_update,
            all_scores,
        )

        t_end = time()

        logger.info(
            f"Project {project.id} scored in {t_end - t0:.2f} seconds."
        )

    return (
        ProjectActionStatus.OK,
        _project_score_success_message(project, passed, passed_ratio),
    )
