from collections.abc import Iterable
from dataclasses import dataclass

from courses.models.project import (
    Project,
    ProjectSubmission,
)
from courses.project_review_scores import calculate_project_score


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
class SubmissionScoringData:
    submission: ProjectSubmission
    project: Project
    reviews: list
    reviewed: list
    criteria: Iterable


def project_lip_score(submission, project) -> int:
    if submission.enrollment.disable_learning_in_public:
        return 0
    if not submission.learning_in_public_links:
        return 0
    links_count = len(submission.learning_in_public_links)
    return min(links_count, project.learning_in_public_cap_project)


def peer_review_lip_score(submission, project, reviewed) -> int:
    if submission.enrollment.disable_learning_in_public:
        return 0
    cap = project.learning_in_public_cap_review
    total = 0
    for review in reviewed:
        if not review.learning_in_public_links:
            continue
        links_count = len(review.learning_in_public_links)
        total += min(links_count, cap)
    return total


def mandatory_reviews_count(reviewed) -> int:
    count = 0
    for review in reviewed:
        if not review.optional:
            count += 1
    return count


def project_faq_score(submission) -> int:
    faq_url = submission.faq_contribution_url
    if faq_url and len(faq_url) >= 5:
        return 1
    return 0


def project_total_score(submission) -> int:
    return (
        submission.project_score
        + submission.project_faq_score
        + submission.project_learning_in_public_score
        + submission.peer_review_score
        + submission.peer_review_learning_in_public_score
    )


def assign_peer_review_scores(submission, project, reviewed) -> int:
    mandatory_count = mandatory_reviews_count(reviewed)
    submission.peer_review_score = (
        mandatory_count * project.points_for_peer_review
    )
    submission.peer_review_learning_in_public_score = (
        peer_review_lip_score(submission, project, reviewed)
    )
    submission.reviewed_enough_peers = (
        mandatory_count >= project.number_of_peers_to_evaluate
    )
    return mandatory_count


def score_submission(data):
    project_score, scores = calculate_project_score(
        submission=data.submission,
        evaluation_criteria=data.criteria,
        reviews=data.reviews,
    )
    data.submission.project_score = project_score

    assign_peer_review_scores(
        data.submission,
        data.project,
        data.reviewed,
    )
    data.submission.project_learning_in_public_score = project_lip_score(
        data.submission,
        data.project,
    )
    data.submission.project_faq_score = project_faq_score(data.submission)
    data.submission.total_score = project_total_score(data.submission)
    data.submission.passed = (
        data.submission.project_score >= data.project.points_to_pass
    ) and data.submission.reviewed_enough_peers

    return scores


def score_project_submissions(data):
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
        scores = score_submission(submission_data)
        all_scores.extend(scores)
        submissions_to_update.append(submission)

        if submission.passed:
            passed += 1

    return ProjectScoringResult(
        submissions_to_update=submissions_to_update,
        evaluation_scores=all_scores,
        passed_count=passed,
    )
