import random
import logging

from time import time
from enum import Enum
from collections import defaultdict

from typing import List, Tuple, Iterable

import math
import statistics

from django.db import transaction
from django.utils import timezone

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


class ProjectActionStatus(Enum):
    OK = "OK"
    FAIL = "Warning"


def pick(selected, projects):
    p = random.choice(projects)

    if p in selected:
        return pick(selected, projects)

    selected.add(p)
    projects.remove(p)
    return p


def select_random_assignment(
    submissions: list[ProjectSubmission],
    num_projects_to_review: int,
    seed: int = 1,
) -> list[PeerReview]:
    n = len(submissions)

    if n <= num_projects_to_review:
        raise ValueError(
            "The number of projects to review should be greater than the number of submissions. "
            + f"Number of projects to review: {num_projects_to_review}, Number of submissions: {n}"
        )

    random.seed(seed)

    submissions_list = list(submissions)

    reviewer = list(range(n))

    projects_pool = []

    for _ in range(num_projects_to_review):
        projects = list(range(n))
        projects_pool.append(projects)

    all_assignments = []

    for r_index in reviewer:
        reviewer_submission = submissions_list[r_index]

        selected = {r_index}

        for i in range(num_projects_to_review):
            projects = projects_pool[i]
            selected_project_index = pick(selected, projects)

            selected_project = submissions_list[selected_project_index]

            assignment = PeerReview(
                submission_under_evaluation=selected_project,
                reviewer=reviewer_submission,
                state=PeerReviewState.TO_REVIEW.value,
                optional=False,
            )

            all_assignments.append(assignment)

    return all_assignments


def assign_peer_reviews_for_project(
    project: Project,
) -> tuple[ProjectActionStatus, str]:
    with transaction.atomic():
        t0 = time()

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

        submissions = ProjectSubmission.objects.filter(
            project=project
        ).select_related("enrollment")

        num_evaluations = project.number_of_peers_to_evaluate
        if submissions.count() <= num_evaluations:
            return (
                ProjectActionStatus.FAIL,
                f"Not enough submissions to assign {num_evaluations} peer reviews each.",
            )

        assignments = select_random_assignment(
            submissions, num_evaluations, seed=42
        )

        PeerReview.objects.bulk_create(assignments)

        project.state = ProjectState.PEER_REVIEWING.value
        project.save()

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

    responses_by_criteria = defaultdict(list)

    for review in reviews:
        for response in review.responses:
            responses_by_criteria[response.criteria_id].append(response)

    for responses in responses_by_criteria.values():
        criteria_score = 0

        scores = []
        for response in responses:
            score = response.get_score()
            scores.append(score)

        criteria = responses[0].criteria
        median_score = statistics.median(scores)
        criteria_score = math.ceil(median_score)

        score = ProjectEvaluationScore(
            submission=submission,
            review_criteria=criteria,
            score=criteria_score,
        )
        new_evaluations.append(score)

        project_score += criteria_score

    return project_score, new_evaluations


def score_project(project: Project) -> tuple[ProjectActionStatus, str]:
    with transaction.atomic():
        t0 = time()

        if project.points_to_pass == 0:
            return (
                ProjectActionStatus.FAIL,
                "Project has no points to pass. Update the course's `project_passing_score` field to greater than zero value",
            )

        if project.state != ProjectState.PEER_REVIEWING.value:
            return (
                ProjectActionStatus.FAIL,
                "Project is not in 'PEER_REVIEWING' state",
            )

        if project.peer_review_due_date > timezone.now():
            return (
                ProjectActionStatus.FAIL,
                "The peer review due date is in the future. Update the due date to score the project.",
            )

        peer_reviews = PeerReview.objects.filter(
            submission_under_evaluation__project=project,
        ).select_related('submission_under_evaluation', 'reviewer')

        if peer_reviews.count() == 0:
            return (
                ProjectActionStatus.FAIL,
                "No peer reviews found for the project.",
            )

        submissions_to_update = []

        criteria_responses = CriteriaResponse.objects.filter(
            review__in=peer_reviews
        ).select_related('criteria')

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
                reviewer = review.reviewer
                reviews_by_reviewer[reviewer.id].append(review)
                review.responses = responses_by_review[review.id]

        criteria = ReviewCriteria.objects.filter(
            course=project.course
        ).all()

        all_scores = []

        passed = 0

        for submission_id, submission in submissions.items():
            reviews = reviews_by_submission[submission_id]

            reviewed = reviews_by_reviewer.get(submission_id)
            if reviewed is None:
                reviewed = []

            project_score, scores = calculate_project_score(
                submission=submission,
                evaluation_criteria=criteria,
                reviews=reviews,
            )
            submission.project_score = project_score
            all_scores.extend(scores)

            num_mandatory_projects_reviewed = 0

            for review in reviewed:
                if not review.optional:
                    num_mandatory_projects_reviewed += 1

            submission.peer_review_score = (
                num_mandatory_projects_reviewed
                * project.points_for_peer_review
            )

            learning_in_public_cap_project = (
                project.learning_in_public_cap_project
            )

            project_learning_in_public_score = 0

            if submission.learning_in_public_links:
                project_learning_in_public_score = len(
                    submission.learning_in_public_links
                )
            if (
                project_learning_in_public_score
                > learning_in_public_cap_project
            ):
                project_learning_in_public_score = (
                    learning_in_public_cap_project
                )

            submission.project_learning_in_public_score = (
                project_learning_in_public_score
            )

            peer_review_learning_in_public_score = 0

            for review in reviewed:
                if not review.learning_in_public_links:
                    continue
                points_for_review = len(review.learning_in_public_links)
                cap = project.learning_in_public_cap_review
                if points_for_review > cap:
                    points_for_review = cap
                peer_review_learning_in_public_score += (
                    points_for_review
                )

            submission.peer_review_learning_in_public_score = (
                peer_review_learning_in_public_score
            )

            submission.project_faq_score = 0

            if (
                submission.faq_contribution
                and len(submission.faq_contribution) >= 5
            ):
                submission.project_faq_score = 1

            submission.total_score = (
                submission.project_score
                + submission.project_faq_score
                + submission.project_learning_in_public_score
                + submission.peer_review_score
                + submission.peer_review_learning_in_public_score
            )

            submission.reviewed_enough_peers = (
                num_mandatory_projects_reviewed
                >= project.number_of_peers_to_evaluate
            )
            submission.passed = (
                submission.project_score >= project.points_to_pass
            ) and submission.reviewed_enough_peers

            submissions_to_update.append(submission)

            if submission.passed:
                passed += 1

        passed_ratio = passed / len(submissions)

        logger.info(
            f"updading {len(submissions_to_update)} submissions..."
        )

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

        scores_to_delete = ProjectEvaluationScore.objects.filter(
            submission_id__in=submissions.keys()
        )
        scores_to_delete.delete()

        ProjectEvaluationScore.objects.bulk_create(all_scores)

        project.state = ProjectState.COMPLETED.value
        project.save()

        update_leaderboard(project.course)

        t_end = time()

        logger.info(
            f"Project {project.id} scored in {t_end - t0:.2f} seconds."
        )

    return (
        ProjectActionStatus.OK,
        f"Project {project.id} scored and state updated to 'COMPLETED'. {passed} passed ({passed_ratio:.2f}).",
    )
