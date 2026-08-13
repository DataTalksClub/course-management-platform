from collections import defaultdict

from courses.models.project import (
    CriteriaResponse,
    PeerReviewState,
    ProjectEvaluationScore,
    ReviewCriteria,
    SystemEvaluationCriteriaResponse,
)
from courses.project_review_scores import score_project_criteria
from courses.project_submission_scoring import project_total_score


def _responses_by_criteria(submission):
    responses_by_criteria = defaultdict(list)
    peer_responses = CriteriaResponse.objects.filter(
        review__submission_under_evaluation=submission,
        review__state=PeerReviewState.SUBMITTED.value,
    ).select_related("criteria")
    system_responses = SystemEvaluationCriteriaResponse.objects.filter(
        evaluation__submission=submission,
    ).select_related("criteria")

    for response in [*peer_responses, *system_responses]:
        responses_by_criteria[response.criteria_id].append(response)
    return responses_by_criteria


def rescore_submission_with_system_evaluations(submission):
    criteria = ReviewCriteria.objects.filter(
        course=submission.project.course,
    ).order_by("id")
    responses_by_criteria = _responses_by_criteria(submission)
    project_score = 0
    evaluation_scores = []

    for criterion in criteria:
        responses = responses_by_criteria.get(criterion.id, [])
        if not responses:
            continue
        criterion_score, evaluation_score = score_project_criteria(
            submission,
            responses,
        )
        project_score += criterion_score
        evaluation_scores.append(evaluation_score)

    ProjectEvaluationScore.objects.filter(submission=submission).delete()
    ProjectEvaluationScore.objects.bulk_create(evaluation_scores)

    submission.project_score = project_score
    submission.total_score = project_total_score(submission)
    submission.passed = (
        submission.project_score >= submission.project.points_to_pass
        and submission.reviewed_enough_peers
    )
    submission.save(
        update_fields=["project_score", "total_score", "passed"]
    )
    return evaluation_scores
