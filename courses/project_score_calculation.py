from dataclasses import dataclass

from courses.models.project import ReviewCriteria
from courses.project_score_groups import group_peer_reviews
from courses.project_submission_scoring import (
    ProjectScoringData,
    score_project_submissions,
)


@dataclass(frozen=True)
class ProjectScoringCalculation:
    submissions: dict
    submissions_to_update: list
    evaluation_scores: list
    passed_count: int


def calculate_project_scoring(project, peer_reviews):
    group_data = group_peer_reviews(peer_reviews)

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
    result = score_project_submissions(scoring_data)

    return ProjectScoringCalculation(
        submissions=group_data.submissions,
        submissions_to_update=result.submissions_to_update,
        evaluation_scores=result.evaluation_scores,
        passed_count=result.passed_count,
    )
