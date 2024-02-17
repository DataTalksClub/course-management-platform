import random

from enum import Enum

from django.db import transaction
from django.utils import timezone

from courses.models import (
    Project,
    ProjectSubmission,
    PeerReview,
    ProjectState,
    PeerReviewState,
)


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
    project_id: str,
) -> tuple[ProjectActionStatus, str]:
    with transaction.atomic():
        project = Project.objects.get(id=project_id)

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

    return (
        ProjectActionStatus.OK,
        f"Peer reviews assigned for project {project_id} and state updated to 'PEER_REVIEWING'.",
    )
