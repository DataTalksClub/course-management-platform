import random
import logging

from time import time
from enum import Enum
from collections import defaultdict

from typing import List, Tuple

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
    random.seed(seed)

    n = len(submissions)

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
        if submissions.count() < num_evaluations:
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


def calculate_project_score(
    submission, reviews: List[PeerReview]
) -> Tuple[int, List[ProjectEvaluationScore]]:
    new_evaluations: List[ProjectEvaluationScore] = []

    project_score = 0

    responses_by_criteria = defaultdict(list)

    for review in reviews:
        for response in review.responses:
            responses_by_criteria[response.criteria_id].append(response)

    for criteria_id, responses in responses_by_criteria.items():
        criteria_score = 0
        scores = [response.score for response in responses]
        median_score = statistics.median(scores)
        criteria_score = math.ceil(median_score)

        score = ProjectEvaluationScore(
            submission=submission,
            criteria_id=criteria_id,
            score=criteria_score,
        )
        new_evaluations.append(score)

        project_score += criteria_score

    return project_score, new_evaluations


def score_project(project: Project) -> tuple[ProjectActionStatus, str]:
    with transaction.atomic():
        t0 = time()

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
            submission_under_evaluation__project=project
        )

        if peer_reviews.count() == 0:
            return (
                ProjectActionStatus.FAIL,
                "No peer reviews found for the project.",
            )

        submissions_to_update = []

        peer_reviews = PeerReview.objects.filter(
            submission_under_evaluation__project=project
        )

        criteria_responses = CriteriaResponse.objects.filter(
            review__in=peer_reviews
        )

        responses_by_review = defaultdict(list)
        for response in criteria_responses:
            responses_by_review[response.review_id].append(response)

        submissions = {}
        reviews_by_submission = defaultdict(list)
        reviews_by_reviewer = defaultdict(list)

        for review in peer_reviews:
            submission = review.submission_under_evaluation
            submissions[submission.id] = submission

            if review.state == PeerReviewState.SUBMITTED.value:
                reviews_by_submission[submission.id].append(review)
                reviewer = review.reviewer
                reviews_by_reviewer[reviewer.id].append(review)
                review.responses = responses_by_review[review.id]

        all_scores = []

        for submission_id, submission in submissions.items():
            reviews = reviews_by_submission[submission_id]

            reviewed = reviews_by_reviewer[submission_id]

            project_score, scores = calculate_project_score(
                submission, reviews
            )
            submission.project_score = project_score
            all_scores.extend(scores)

            num_projects_reviewed = len(reviewed)

            submission.peer_review_score = (
                num_projects_reviewed * project.points_for_peer_review
            )

            learning_in_public_cap_project = (
                project.learning_in_public_cap_project
            )

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

            submission.peer_review_learning_in_public_score = (
                project_learning_in_public_score
            )

            peer_review_learning_in_public_score = 0

            for review in reviews:
                poinst_for_review = len(review.learning_in_public_links)
                cap = project.learning_in_public_cap_review
                if poinst_for_review > cap:
                    poinst_for_review = cap
                peer_review_learning_in_public_score += (
                    poinst_for_review
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
                num_projects_reviewed
                >= project.number_of_peers_to_evaluate
            )
            submission.passed = (
                (submission.project_score >= project.points_to_pass) 
                and submission.reviewed_enough_peers
            )

        ProjectSubmission.objects.bulk_update(
            submissions_to_update,
            [
                "project_score",
                "project_faq_score",
                "project_learning_in_public_score",
                "peer_review_score",
                "peer_review_faq_score",
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
        f"Project {project.id} scored and state updated to 'COMPLETED'.",
    )
