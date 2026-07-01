from dataclasses import dataclass

from courses.models.project import Project, ProjectState, ProjectSubmission
from courses.views.project_submission_viewer import ProjectViewerState
from courses.votes import PROJECT_VOTES_PER_PROJECT


@dataclass(frozen=True)
class ProjectSubmissionsDecorationData:
    submissions_list: list
    project: Project
    viewer_state: ProjectViewerState


@dataclass(frozen=True)
class SubmissionViewerStateData:
    submission: ProjectSubmission
    decoration: ProjectSubmissionsDecorationData


@dataclass(frozen=True)
class SubmissionReviewGroupData:
    submission: ProjectSubmission
    in_peer_review: bool
    decoration: ProjectSubmissionsDecorationData


def decorate_project_submissions(data):
    viewer_state = data.viewer_state
    in_peer_review = (
        viewer_state.is_authenticated
        and data.project.state == ProjectState.PEER_REVIEWING.value
    )

    for order, submission in enumerate(data.submissions_list):
        submission.list_order = order
        _decorate_submission_review_state(
            submission,
            viewer_state.review_ids,
        )
        viewer_data = SubmissionViewerStateData(
            submission=submission,
            decoration=data,
        )
        _decorate_submission_viewer_state(viewer_data)
        review_group_data = SubmissionReviewGroupData(
            submission=submission,
            in_peer_review=in_peer_review,
            decoration=data,
        )
        _decorate_submission_review_group(review_group_data)


def _project_submission_review_group_sort_key(submission):
    return submission.group_order, submission.list_order


def sort_project_submissions_for_view(
    submissions_list,
    *,
    project,
    viewer_state,
):
    if _project_submissions_use_review_group_sort(project, viewer_state):
        submissions_list.sort(key=_project_submission_review_group_sort_key)


def apply_project_group_headings(submissions_page):
    previous_group_label = None
    submissions = submissions_page.object_list
    for submission in submissions:
        submission.group_heading = None
        if (
            submission.group_label
            and submission.group_label != previous_group_label
        ):
            submission.group_heading = submission.group_label
        previous_group_label = submission.group_label


def _decorate_submission_review_state(submission, review_ids):
    if submission.id in review_ids:
        submission.to_evaluate = True
        submission.review = review_ids[submission.id]
        return

    submission.to_evaluate = False


def _decorate_submission_viewer_state(data):
    viewer_state = data.decoration.viewer_state
    project = data.decoration.project
    data.submission.own = data.submission.id in viewer_state.own_submissions
    data.submission.vote_limit_reached = (
        data.submission.id not in viewer_state.voted_submission_ids
        and viewer_state.project_vote_counts.get(project.id, 0)
        >= PROJECT_VOTES_PER_PROJECT
    )


def _decorate_submission_review_group(data):
    submission = data.submission
    submission.group_order = 1
    submission.group_label = None

    if not data.in_peer_review:
        return

    if submission.to_evaluate and not submission.review.optional:
        submission.group_order = 0
        submission.group_label = "Assigned reviews"
        return

    if data.decoration.viewer_state.has_assigned_reviews:
        submission.group_label = "Other submissions"


def _project_submissions_use_review_group_sort(project, viewer_state):
    return (
        viewer_state.is_authenticated
        and project.state == ProjectState.PEER_REVIEWING.value
    )
