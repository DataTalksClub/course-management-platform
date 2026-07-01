from collections import defaultdict
from dataclasses import dataclass

from courses.models import CriteriaResponse, PeerReviewState


@dataclass(frozen=True)
class PeerReviewGroupData:
    responses_by_review: dict
    submissions: dict
    reviews_by_submission: dict
    reviews_by_reviewer: dict


def criteria_responses_by_review(peer_reviews):
    criteria_responses = CriteriaResponse.objects.filter(
        review__in=peer_reviews
    ).select_related("criteria")

    responses_by_review = defaultdict(list)
    for response in criteria_responses:
        responses_by_review[response.review_id].append(response)
    return responses_by_review


def ensure_peer_review_groups(
    review,
    group_data,
):
    submission = review.submission_under_evaluation
    group_data.submissions[submission.id] = submission
    group_data.reviews_by_submission.setdefault(submission.id, [])
    group_data.reviews_by_reviewer.setdefault(review.reviewer.id, [])
    return submission


def attach_submitted_peer_review(
    review,
    submission,
    group_data,
):
    if review.state != PeerReviewState.SUBMITTED.value:
        return

    group_data.reviews_by_submission[submission.id].append(review)
    group_data.reviews_by_reviewer[review.reviewer.id].append(review)
    review.responses = group_data.responses_by_review[review.id]


def group_peer_reviews(peer_reviews):
    responses_by_review = criteria_responses_by_review(peer_reviews)
    submissions = {}
    reviews_by_submission = {}
    reviews_by_reviewer = {}
    group_data = PeerReviewGroupData(
        responses_by_review=responses_by_review,
        submissions=submissions,
        reviews_by_submission=reviews_by_submission,
        reviews_by_reviewer=reviews_by_reviewer,
    )

    for review in peer_reviews:
        submission = ensure_peer_review_groups(
            review,
            group_data,
        )
        attach_submitted_peer_review(
            review,
            submission,
            group_data,
        )

    return group_data
