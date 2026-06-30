from collections.abc import Iterable
from dataclasses import dataclass

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from courses.models import (
    Course,
    CriteriaResponse,
    Enrollment,
    PeerReview,
    PeerReviewState,
    Project,
    ProjectState,
    ReviewCriteria,
)
from courses.votes import (
    PROJECT_VOTES_PER_PROJECT,
    get_project_vote_counts,
    get_voted_submission_ids,
    update_project_vote,
)

from .homework_learning_links import clean_learning_in_public_links


@dataclass(frozen=True)
class ProjectEvalSubmitPage:
    course: Course
    project: Project
    review: PeerReview
    review_criteria: Iterable[ReviewCriteria]


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


def project_eval_accepting_submissions(project):
    return project.state == ProjectState.PEER_REVIEWING.value


def project_eval_disable_learning_in_public(enrollment):
    if enrollment is None:
        return False
    return enrollment.disable_learning_in_public


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


def project_eval_answers_from_post(post_data):
    answers = {}
    posted_answers = post_data.lists()
    for answer_id, answer in posted_answers:
        if not answer_id.startswith("answer_"):
            continue
        cleaned_answer_items = []
        for value in answer:
            cleaned_value = value.strip()
            cleaned_answer_items.append(cleaned_value)
        answers[answer_id] = ",".join(cleaned_answer_items)
    return answers


def save_project_eval_criteria_responses(
    review,
    review_criteria,
    answers_by_field,
):
    for criteria in review_criteria:
        answer = answers_by_field.get(f"answer_{criteria.id}")
        CriteriaResponse.objects.update_or_create(
            review=review,
            criteria=criteria,
            defaults={"answer": answer},
        )


def apply_review_learning_in_public_links(request, project, review):
    if project.learning_in_public_cap_review <= 0:
        return

    links = request.POST.getlist("learning_in_public_links[]")
    review.learning_in_public_links = clean_learning_in_public_links(
        links,
        project.learning_in_public_cap_review,
    )


def apply_review_time_spent(request, project, review):
    if not project.time_spent_evaluation_field:
        return

    time_spent_reviewing = request.POST.get("time_spent_reviewing")
    if time_spent_reviewing is not None and time_spent_reviewing != "":
        review.time_spent_reviewing = float(time_spent_reviewing)


def apply_review_problems_comments(request, project, review):
    if project.problems_comments_field:
        problems_comments = request.POST.get("problems_comments", "")
        review.problems_comments = problems_comments.strip()


def apply_review_note_to_peer(request, review):
    note_to_peer = request.POST.get("note_to_peer", "")
    review.note_to_peer = note_to_peer.strip()


def submit_project_review(review):
    review.submitted_at = timezone.now()
    review.state = PeerReviewState.SUBMITTED.value
    review.save()


def project_eval_post_submission(
    request: HttpRequest,
    project: Project,
    review: PeerReview,
    review_criteria: Iterable[ReviewCriteria],
) -> None:
    answers_by_field = project_eval_answers_from_post(request.POST)
    save_project_eval_criteria_responses(
        review,
        review_criteria,
        answers_by_field,
    )
    apply_review_learning_in_public_links(request, project, review)
    apply_review_time_spent(request, project, review)
    apply_review_problems_comments(request, project, review)
    apply_review_note_to_peer(request, review)
    submit_project_review(review)

    messages.success(
        request,
        "Thank you for submitting your evaluation, it is now saved. You can update it at any point.",
        extra_tags="homework",
    )


def project_eval_submit_context(request, page: ProjectEvalSubmitPage):
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
    return context


def project_eval_vote_response(request, course_slug, project_slug, review):
    action = request.POST.get("action", "vote")
    update_project_vote(
        request.user,
        review.submission_under_evaluation,
        action=action,
    )
    response = redirect(
        "projects_eval_submit",
        course_slug=course_slug,
        project_slug=project_slug,
        review_id=review.id,
    )
    return response


def closed_project_eval_response(
    request,
    page: ProjectEvalSubmitPage,
):
    messages.error(
        request,
        "Peer review form is closed.",
        extra_tags="homework",
    )
    context = project_eval_submit_context(request, page)
    response = render(request, "projects/eval_submit.html", context)
    return response


def projects_eval_submit_post_response(
    request,
    page: ProjectEvalSubmitPage,
):
    if request.POST.get("form_action") == "vote":
        return project_eval_vote_response(
            request,
            page.course.slug,
            page.project.slug,
            page.review,
        )

    if page.project.state != ProjectState.PEER_REVIEWING.value:
        return closed_project_eval_response(
            request,
            page,
        )

    project_eval_post_submission(
        request,
        page.project,
        page.review,
        page.review_criteria,
    )
    response = redirect(
        "projects_eval",
        course_slug=page.course.slug,
        project_slug=page.project.slug,
    )
    return response


def project_eval_submit_page(
    course_slug,
    project_slug,
    review,
) -> ProjectEvalSubmitPage:
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, slug=project_slug, course=course
    )
    review_criteria = ReviewCriteria.objects.filter(
        course=course
    ).order_by("id")
    return ProjectEvalSubmitPage(
        course=course,
        project=project,
        review=review,
        review_criteria=review_criteria,
    )


@login_required
def projects_eval_submit(request, course_slug, project_slug, review_id):
    review = get_object_or_404(PeerReview, id=review_id)

    if review.reviewer.student != request.user:
        messages.error(
            request,
            "You are not allowed to evaluate this submission, choose a different one.",
            extra_tags="homework",
        )
        response = redirect(
            "projects_eval",
            course_slug=course_slug,
            project_slug=project_slug,
        )
        return response

    page = project_eval_submit_page(course_slug, project_slug, review)

    if request.method == "POST":
        return projects_eval_submit_post_response(
            request,
            page,
        )

    context = project_eval_submit_context(
        request,
        page,
    )

    response = render(request, "projects/eval_submit.html", context)
    return response
