import logging

from dataclasses import dataclass
from time import time
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
from .project_assignment import (
    ProjectActionStatus,
    assign_peer_reviews_for_project as assign_peer_reviews_for_project,
    select_random_assignment as select_random_assignment,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PeerReviewGroupData:
    responses_by_review: dict
    submissions: dict
    reviews_by_submission: dict
    reviews_by_reviewer: dict


@dataclass(frozen=True)
class ProjectScoringData:
    project: Project
    submissions: dict
    reviews_by_submission: dict
    reviews_by_reviewer: dict
    criteria: Iterable


@dataclass(frozen=True)
class ProjectScoringResult:
    submissions_to_update: list
    evaluation_scores: list
    passed_count: int


@dataclass(frozen=True)
class ProjectScoringCalculation:
    submissions: dict
    submissions_to_update: list
    evaluation_scores: list
    passed_count: int


@dataclass(frozen=True)
class SubmissionScoringData:
    submission: ProjectSubmission
    project: Project
    reviews: list
    reviewed: list
    criteria: Iterable


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

    criteria_responses = responses_by_criteria.values()
    for responses in criteria_responses:
        criteria_score, evaluation = score_project_criteria(
            submission, responses
        )
        new_evaluations.append(evaluation)
        project_score += criteria_score

    return project_score, new_evaluations


def responses_grouped_by_criteria(reviews: List[PeerReview]):
    responses_by_criteria = defaultdict(list)
    for review in reviews:
        responses = review.responses
        for response in responses:
            responses_by_criteria[response.criteria_id].append(response)
    return responses_by_criteria


def score_project_criteria(
    submission: ProjectSubmission,
    responses: list[CriteriaResponse],
) -> tuple[int, ProjectEvaluationScore]:
    criteria = responses[0].criteria
    scores = []
    for response in responses:
        score = response.get_score()
        scores.append(score)
    median_score = statistics.median(scores)
    criteria_score = math.ceil(median_score)
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


def _criteria_responses_by_review(peer_reviews):
    criteria_responses = CriteriaResponse.objects.filter(
        review__in=peer_reviews
    ).select_related("criteria")

    responses_by_review = defaultdict(list)
    for response in criteria_responses:
        responses_by_review[response.review_id].append(response)
    return responses_by_review


def _ensure_peer_review_groups(
    review,
    group_data,
):
    submission = review.submission_under_evaluation
    group_data.submissions[submission.id] = submission
    group_data.reviews_by_submission.setdefault(submission.id, [])
    group_data.reviews_by_reviewer.setdefault(review.reviewer.id, [])
    return submission


def _attach_submitted_peer_review(
    review,
    submission,
    group_data,
):
    if review.state != PeerReviewState.SUBMITTED.value:
        return

    group_data.reviews_by_submission[submission.id].append(review)
    group_data.reviews_by_reviewer[review.reviewer.id].append(review)
    review.responses = group_data.responses_by_review[review.id]


def _group_peer_reviews(peer_reviews):
    """Group submitted peer reviews by submission and by reviewer.

    Also attaches each submitted review's criteria responses as
    ``review.responses``.
    """
    responses_by_review = _criteria_responses_by_review(peer_reviews)
    submissions = {}
    reviews_by_submission = {}
    reviews_by_reviewer = {}
    group_data = PeerReviewGroupData(
        responses_by_review=responses_by_review,
        submissions=submissions,
        reviews_by_submission=reviews_by_submission,
        reviews_by_reviewer=reviews_by_reviewer,
    )

    for review in peer_reviews:
        submission = _ensure_peer_review_groups(
            review,
            group_data,
        )
        _attach_submitted_peer_review(
            review,
            submission,
            group_data,
        )

    return group_data


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
    count = 0
    for review in reviewed:
        if not review.optional:
            count += 1
    return count


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


def _score_submission(data):
    """Compute and assign every score component for a single submission.

    Mutates ``data.submission`` in place and returns the per-criteria
    ProjectEvaluationScore objects produced for it.
    """
    project_score, scores = calculate_project_score(
        submission=data.submission,
        evaluation_criteria=data.criteria,
        reviews=data.reviews,
    )
    data.submission.project_score = project_score

    _assign_peer_review_scores(
        data.submission,
        data.project,
        data.reviewed,
    )
    data.submission.project_learning_in_public_score = (
        _project_lip_score(data.submission, data.project)
    )
    data.submission.project_faq_score = _project_faq_score(data.submission)
    data.submission.total_score = _project_total_score(data.submission)
    data.submission.passed = (
        data.submission.project_score >= data.project.points_to_pass
    ) and data.submission.reviewed_enough_peers

    return scores


def _sync_scored_project_submission_to_datamailer(submission):
    sync_project_submission_to_datamailer(submission)
    sync_project_passed_outcome_to_datamailer(submission)


def _peer_reviews_for_project(project):
    return PeerReview.objects.filter(
        submission_under_evaluation__project=project,
    ).select_related("submission_under_evaluation", "reviewer")


def _score_project_submissions(data):
    submissions_to_update = []
    all_scores = []
    passed = 0

    for submission_id, submission in data.submissions.items():
        reviews = data.reviews_by_submission[submission_id]
        reviewed = data.reviews_by_reviewer.get(submission_id) or []

        submission_data = SubmissionScoringData(
            submission=submission,
            project=data.project,
            reviews=reviews,
            reviewed=reviewed,
            criteria=data.criteria,
        )
        scores = _score_submission(submission_data)
        all_scores.extend(scores)
        submissions_to_update.append(submission)

        if submission.passed:
            passed += 1

    return ProjectScoringResult(
        submissions_to_update=submissions_to_update,
        evaluation_scores=all_scores,
        passed_count=passed,
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
    group_data = _group_peer_reviews(peer_reviews)

    criteria = ReviewCriteria.objects.filter(
        course=project.course
    ).all()

    scoring_data = ProjectScoringData(
        project=project,
        submissions=group_data.submissions,
        reviews_by_submission=group_data.reviews_by_submission,
        reviews_by_reviewer=group_data.reviews_by_reviewer,
        criteria=criteria,
    )
    result = _score_project_submissions(scoring_data)

    return ProjectScoringCalculation(
        submissions=group_data.submissions,
        submissions_to_update=result.submissions_to_update,
        evaluation_scores=result.evaluation_scores,
        passed_count=result.passed_count,
    )


def _complete_scored_project(
    project,
    calculation,
):
    _bulk_update_project_submissions(calculation.submissions_to_update)
    _sync_project_submissions_after_commit(calculation.submissions_to_update)
    _replace_project_evaluation_scores(
        calculation.submissions.keys(),
        calculation.evaluation_scores,
    )

    project.state = ProjectState.COMPLETED.value
    project.save()

    update_leaderboard(project.course)


def _project_score_success_message(project, passed, passed_ratio):
    return (
        f"Project {project.id} scored and state updated to "
        f"'COMPLETED'. {passed} passed ({passed_ratio:.2f})."
    )


def _project_scoreable_peer_reviews(project):
    error = _validate_project_scoreable(project)
    if error is not None:
        return None, error

    peer_reviews = _peer_reviews_for_project(project)
    if peer_reviews.count() == 0:
        return None, "No peer reviews found for the project."

    return peer_reviews, None


def _score_project_with_reviews(project, peer_reviews):
    calculation = _calculate_project_scoring(project, peer_reviews)
    passed_ratio = calculation.passed_count / len(calculation.submissions)

    _complete_scored_project(
        project,
        calculation,
    )

    return _project_score_success_message(
        project,
        calculation.passed_count,
        passed_ratio,
    )


def score_project(project: Project) -> tuple[ProjectActionStatus, str]:
    with transaction.atomic():
        t0 = time()

        peer_reviews, error = _project_scoreable_peer_reviews(project)
        if error is not None:
            return (ProjectActionStatus.FAIL, error)

        success_message = _score_project_with_reviews(project, peer_reviews)

        t_end = time()

        logger.info(
            f"Project {project.id} scored in {t_end - t0:.2f} seconds."
        )

    return (ProjectActionStatus.OK, success_message)
