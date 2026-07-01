from courses.models.project import PeerReview, ProjectSubmission
from courses.votes import (
    PROJECT_VOTES_PER_PROJECT,
    get_project_vote_counts,
    get_voted_submission_ids,
)


def project_viewer_state(project, course, user):
    vote_state = _project_viewer_vote_state(project, course, user)
    state = _base_project_viewer_state(vote_state)

    if not user.is_authenticated:
        return state

    state["is_authenticated"] = True
    student_submissions, own_submissions = (
        _project_viewer_student_submissions(project, user)
    )
    review_ids, has_assigned_reviews = _project_viewer_reviews(
        project,
        student_submissions,
    )

    state.update(
        {
            "review_ids": review_ids,
            "own_submissions": own_submissions,
            "has_submission": len(own_submissions) > 0,
            "has_assigned_reviews": has_assigned_reviews,
        }
    )
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


def _base_project_viewer_state(vote_state):
    own_submissions = set()
    return {
        "is_authenticated": False,
        "review_ids": {},
        "own_submissions": own_submissions,
        "has_submission": False,
        **vote_state,
        "has_assigned_reviews": False,
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
