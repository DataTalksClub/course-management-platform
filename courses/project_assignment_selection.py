import random

from courses.models.project import (
    PeerReview,
    PeerReviewState,
    ProjectSubmission,
)


def select_random_assignment(
    submissions: list[ProjectSubmission],
    num_projects_to_review: int,
    seed: int = 1,
) -> list[PeerReview]:
    num_submissions = len(submissions)
    _validate_peer_review_assignment_size(
        num_submissions,
        num_projects_to_review,
    )
    random.seed(seed)

    submissions_list = list(submissions)
    projects_pool = _review_slot_project_pools(
        num_submissions, num_projects_to_review
    )

    all_assignments = []
    for reviewer_idx, reviewer_submission in enumerate(submissions_list):
        assignments = _select_reviewer_assignments(
            reviewer_idx,
            reviewer_submission,
            submissions_list,
            projects_pool,
        )
        all_assignments.extend(assignments)

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
    project_pools = []
    for _ in range(num_projects_to_review):
        project_pool = list(range(num_submissions))
        project_pools.append(project_pool)
    return project_pools


def _select_reviewer_assignments(
    reviewer_idx: int,
    reviewer_submission: ProjectSubmission,
    submissions: list[ProjectSubmission],
    projects_pool: list[list[int]],
) -> list[PeerReview]:
    selected = {reviewer_idx}
    assignments = []
    num_submissions = len(submissions)

    for projects in projects_pool:
        selected_project_idx = _select_project_for_review(
            projects,
            selected,
            num_submissions,
        )
        selected.add(selected_project_idx)
        _remove_project_from_slot_pool(selected_project_idx, projects)
        selected_project = submissions[selected_project_idx]
        assignment = PeerReview(
            submission_under_evaluation=selected_project,
            reviewer=reviewer_submission,
            state=PeerReviewState.TO_REVIEW.value,
            optional=False,
        )
        assignments.append(assignment)

    return assignments


def _select_project_for_review(
    projects: list[int],
    selected: set[int],
    num_submissions: int,
) -> int:
    available = _available_review_projects(projects, selected)
    if not available:
        available = _fallback_review_projects(selected, num_submissions)
    return random.choice(available)


def _available_review_projects(
    projects: list[int],
    selected: set[int],
) -> list[int]:
    available_projects = []
    for project in projects:
        if project not in selected:
            available_projects.append(project)
    return available_projects


def _fallback_review_projects(
    selected: set[int],
    num_submissions: int,
) -> list[int]:
    fallback_projects = []
    for project in range(num_submissions):
        if project not in selected:
            fallback_projects.append(project)
    return fallback_projects


def _remove_project_from_slot_pool(
    project_idx: int,
    projects: list[int],
) -> None:
    if project_idx in projects:
        projects.remove(project_idx)
