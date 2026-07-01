from collections.abc import Iterable
from dataclasses import dataclass

from django.http import HttpRequest

from courses.models import (
    Course,
    Enrollment,
    PeerReview,
    Project,
    ProjectState,
    ReviewCriteria,
)
from courses.votes import (
    PROJECT_VOTES_PER_PROJECT,
    get_project_vote_counts,
    get_voted_submission_ids,
)


@dataclass(frozen=True)
class ProjectEvalSubmitPage:
    course: Course
    project: Project
    review: PeerReview
    review_criteria: Iterable[ReviewCriteria]


def project_eval_submit_context(
    request: HttpRequest, page: ProjectEvalSubmitPage
):
    enrollment, _ = Enrollment.objects.get_or_create(
        student=request.user,
        course=page.course,
    )
    context = project_eval_build_context(
        page.project,
        page.review,
        page.review_criteria,
        enrollment,
    )
    context["course"] = page.course
    add_project_eval_vote_context(request, page, context)
    return context


def project_eval_build_context(
    project: Project,
    review: PeerReview,
    review_criteria: Iterable[ReviewCriteria],
    enrollment: Enrollment | None = None,
):
    submission = review.submission_under_evaluation
    accepting_submissions = project_eval_accepting_submissions(project)
    disabled = not accepting_submissions
    responses_by_criteria_id = project_eval_responses_by_criteria_id(review)
    criteria_response_pairs = project_eval_criteria_response_pairs(
        review_criteria,
        responses_by_criteria_id,
    )
    disable_learning_in_public = project_eval_disable_learning_in_public(
        enrollment
    )

    context = {
        "project": project,
        "review": review,
        "submission": submission,
        "criteria_response_pairs": criteria_response_pairs,
        "accepting_submissions": accepting_submissions,
        "disabled": disabled,
        "disable_learning_in_public": disable_learning_in_public,
    }

    return context


def add_project_eval_vote_context(request, page, context):
    voted_submission_ids = get_voted_submission_ids(
        request.user,
        page.course,
    )
    context["voted_submission_ids"] = voted_submission_ids
    project_vote_counts = get_project_vote_counts(request.user, page.course)
    submission = context["submission"]
    project_votes_count = project_vote_counts.get(submission.project_id, 0)
    vote_limit_reached = (
        submission.id not in voted_submission_ids
        and project_votes_count >= PROJECT_VOTES_PER_PROJECT
    )
    context["vote_limit_reached"] = vote_limit_reached
    context["project_votes_per_project"] = PROJECT_VOTES_PER_PROJECT


def project_eval_criteria_response_pairs(
    review_criteria,
    responses_by_criteria_id,
):
    criteria_response_pairs = []
    for criteria in review_criteria:
        response = responses_by_criteria_id.get(criteria.id)
        selected_indexes = criteria_response_answer_indexes(response)
        annotate_criteria_options(criteria, selected_indexes)
        criteria_response_pair = (criteria, response)
        criteria_response_pairs.append(criteria_response_pair)
    return criteria_response_pairs


def project_eval_responses_by_criteria_id(review):
    responses_by_criteria_id = {}
    criteria_responses = review.get_criteria_responses()
    for response in criteria_responses:
        responses_by_criteria_id[response.criteria.id] = response
    return responses_by_criteria_id


def criteria_response_answer_indexes(response):
    if response is None:
        return set()

    raw_answer = response.answer or ""
    stripped_answer = raw_answer.strip()
    answers = stripped_answer.split(",")
    answer_indexes = set()
    for answer in answers:
        if answer:
            answer_index = int(answer)
            answer_indexes.add(answer_index)
    return answer_indexes


def annotate_criteria_options(criteria, selected_indexes):
    for index, option in enumerate(criteria.options, start=1):
        option["index"] = index
        option["is_selected"] = index in selected_indexes


def project_eval_accepting_submissions(project):
    return project.state == ProjectState.PEER_REVIEWING.value


def project_eval_disable_learning_in_public(enrollment):
    if enrollment is None:
        return False
    return enrollment.disable_learning_in_public
