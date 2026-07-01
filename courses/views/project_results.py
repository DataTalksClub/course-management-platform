from collections import defaultdict

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404, render

from courses.models import (
    Course,
    CriteriaResponse,
    PeerReview,
    PeerReviewState,
    Project,
    ProjectEvaluationScore,
    ProjectSubmission,
)


def answer_option_indexes(answer: str) -> list[int]:
    if not answer:
        return []

    indexes = []
    values = answer.split(",")
    for value in values:
        value = value.strip()
        if value:
            option_number = int(value)
            option_index = option_number - 1
            indexes.append(option_index)
    return indexes


def _criteria_responses_for_scores(
    submission: ProjectSubmission,
    scores: list[ProjectEvaluationScore],
) -> QuerySet[CriteriaResponse]:
    criteria_ids = []
    for score in scores:
        criteria_id = score.review_criteria_id
        criteria_ids.append(criteria_id)
    return CriteriaResponse.objects.filter(
        review__submission_under_evaluation=submission,
        review__state=PeerReviewState.SUBMITTED.value,
        criteria_id__in=criteria_ids,
    )


def _option_votes_by_criteria(responses):
    votes_by_criteria = {}
    for response in responses:
        votes = votes_by_criteria.get(response.criteria_id)
        if votes is None:
            votes = defaultdict(int)
            votes_by_criteria[response.criteria_id] = votes
        option_indexes = answer_option_indexes(response.answer)
        for option_index in option_indexes:
            votes[option_index] += 1
    return votes_by_criteria


def _score_option_vote_counts(score, option_votes):
    vote_counts = []
    for index, option in enumerate(score.review_criteria.options):
        option_vote_count = option.copy()
        option_vote_count["votes"] = option_votes[index]
        vote_counts.append(option_vote_count)
    return vote_counts


def annotate_scores_with_option_votes(
    submission: ProjectSubmission,
    scores: list[ProjectEvaluationScore],
) -> None:
    responses = _criteria_responses_for_scores(submission, scores)
    votes_by_criteria = _option_votes_by_criteria(responses)
    for score in scores:
        score.option_vote_counts = _score_option_vote_counts(
            score,
            votes_by_criteria[score.review_criteria_id],
        )


def project_results(request, course_slug, project_slug):
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )
    context = _project_results_context(course, project, request.user)

    response = render(request, "projects/results.html", context)
    return response


def _project_results_context(course, project, user):
    if not user.is_authenticated:
        return _anonymous_project_results_context(course, project)

    submission = _project_results_submission(project, user)
    scores = _project_results_scores(submission)
    feedback = _project_results_feedback(submission)
    return {
        "course": course,
        "project": project,
        "submission": submission,
        "scores": scores,
        "feedback": feedback,
        "is_authenticated": True,
    }


def _anonymous_project_results_context(course, project):
    return {
        "course": course,
        "project": project,
        "is_authenticated": False,
    }


def _project_results_submission(project, user):
    return ProjectSubmission.objects.filter(
        project=project,
        student=user,
        volunteer_review_only=False,
    ).first()


def _project_results_scores(submission):
    scores = ProjectEvaluationScore.objects.filter(submission=submission)
    scores = scores.order_by("review_criteria__id")
    scores = scores.prefetch_related("review_criteria")
    scores_list = list(scores)
    annotate_scores_with_option_votes(submission, scores_list)
    return scores_list


def _project_results_feedback(submission):
    feedback = PeerReview.objects.filter(
        submission_under_evaluation=submission,
        state=PeerReviewState.SUBMITTED.value,
        note_to_peer__isnull=False,
        note_to_peer__gt="",
    )
    return list(feedback)
