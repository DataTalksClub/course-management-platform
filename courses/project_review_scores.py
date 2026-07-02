import logging
import math
import statistics
from collections import defaultdict
from collections.abc import Iterable

from courses.models.project import (
    CriteriaResponse,
    PeerReview,
    ProjectEvaluationScore,
    ProjectSubmission,
    ReviewCriteria,
)


logger = logging.getLogger(__name__)


def calculate_median_score(
    submission: ProjectSubmission,
    evaluation_criteria: list[ReviewCriteria],
) -> tuple[int, list[ProjectEvaluationScore]]:
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
    reviews: list[PeerReview],
) -> tuple[int, list[ProjectEvaluationScore]]:
    if len(reviews) == 0:
        logger.info(f"No reviews found for submission {submission.id}")
        return calculate_median_score(submission, evaluation_criteria)

    new_evaluations: list[ProjectEvaluationScore] = []

    project_score = 0
    responses_by_criteria = responses_grouped_by_criteria(reviews)

    for responses in responses_by_criteria.values():
        criteria_score, evaluation = score_project_criteria(
            submission, responses
        )
        new_evaluations.append(evaluation)
        project_score += criteria_score

    return project_score, new_evaluations


def responses_grouped_by_criteria(reviews: list[PeerReview]):
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
    scores = []
    for response in responses:
        score = response.get_score()
        scores.append(score)
    median_score = statistics.median(scores)
    criteria_score = math.ceil(median_score)
    evaluation_score = ProjectEvaluationScore(
        submission=submission,
        review_criteria=criteria,
        score=criteria_score,
    )
    return criteria_score, evaluation_score
