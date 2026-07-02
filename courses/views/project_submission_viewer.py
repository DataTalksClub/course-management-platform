from dataclasses import dataclass, field

from courses.models.project import PeerReview, ProjectSubmission
from courses.votes import (
    PROJECT_VOTES_PER_PROJECT,
    get_project_vote_counts,
    get_voted_submission_ids,
)


@dataclass
class ProjectViewerState:
    voted_submission_ids: set
    project_vote_counts: dict
    project_votes_left: int
    is_authenticated: bool = False
    review_ids: dict = field(default_factory=dict)
    own_submissions: set = field(default_factory=set)
    has_submission: bool = False
    has_assigned_reviews: bool = False


def project_viewer_state(project, course, user):
    vote_state = _project_viewer_vote_state(project, course, user)
    state = ProjectViewerState(
        voted_submission_ids=vote_state["voted_submission_ids"],
        project_vote_counts=vote_state["project_vote_counts"],
        project_votes_left=vote_state["project_votes_left"],
    )

    if not user.is_authenticated:
        return state

    state.is_authenticated = True
    student_submissions, own_submissions = (
        _project_viewer_student_submissions(project, user)
    )
    review_ids, has_assigned_reviews = _project_viewer_reviews(
        project,
        student_submissions,
    )

    state.review_ids = review_ids
    state.own_submissions = own_submissions
    state.has_submission = len(own_submissions) > 0
    state.has_assigned_reviews = has_assigned_reviews
    return state


def _project_viewer_vote_state(project, course, user):
    voted_submission_ids = get_voted_submission_ids(user, course)
    project_vote_counts = get_project_vote_counts(user, course)
    project_vote_count = project_vote_counts.get(project.id, 0)
    project_votes_left = max(
        PROJECT_VOTES_PER_PROJECT - project_vote_count,
        0,
    )
    return {
        "voted_submission_ids": voted_submission_ids,
        "project_vote_counts": project_vote_counts,
        "project_votes_left": project_votes_left,
    }

def _project_viewer_student_submissions(project, user):
    student_submissions = ProjectSubmission.objects.filter(
        project=project, student=user
    )
    project_submissions = student_submissions.filter(
        volunteer_review_only=False,
    )
    own_submission_ids = project_submissions.values_list("id", flat=True)
    own_submissions = set(own_submission_ids)
    return student_submissions, own_submissions


def _project_viewer_reviews(project, student_submissions):
    review_ids = {}
    has_assigned_reviews = False
    reviews = PeerReview.objects.filter(
        reviewer__in=student_submissions,
        submission_under_evaluation__project=project,
    )
    for review in reviews:
        eval_id = review.submission_under_evaluation_id
        review_ids[eval_id] = review
        if not review.optional:
            has_assigned_reviews = True

    return review_ids, has_assigned_reviews
