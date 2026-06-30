from collections.abc import Iterable
from dataclasses import dataclass
from typing import Optional

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
    ProjectSubmission,
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


@dataclass(frozen=True)
class ProjectEvalReviewGroups:
    assigned_reviews: list
    selected_reviews: list
    completed_count: int

def anonymous_project_eval_context(course, project, eval_closed):
    return {
        "course": course,
        "project": project,
        "is_authenticated": False,
        "eval_closed": eval_closed,
    }


def student_project_submissions(project, user):
    return ProjectSubmission.objects.filter(project=project, student=user)


def project_eval_reviews(project, student_submissions):
    return PeerReview.objects.filter(
        reviewer__in=student_submissions,
        submission_under_evaluation__project=project,
    ).order_by("optional")


def split_project_eval_reviews(reviews):
    assigned_reviews = []
    selected_reviews = []
    completed_count = 0

    for review in reviews:
        if review.optional:
            selected_reviews.append(review)
            continue
        assigned_reviews.append(review)
        if review.state == PeerReviewState.SUBMITTED.value:
            completed_count += 1

    return ProjectEvalReviewGroups(
        assigned_reviews=assigned_reviews,
        selected_reviews=selected_reviews,
        completed_count=completed_count,
    )


def student_project_eval_context(course, project, user, eval_closed):
    student_submissions = student_project_submissions(project, user)
    project_submissions = student_submissions.filter(
        volunteer_review_only=False,
    )
    reviews = project_eval_reviews(project, student_submissions)
    review_groups = split_project_eval_reviews(reviews)

    return {
        "course": course,
        "project": project,
        "reviews": reviews,
        "assigned_reviews": review_groups.assigned_reviews,
        "selected_reviews": review_groups.selected_reviews,
        "is_authenticated": True,
        "number_of_completed_evaluation": review_groups.completed_count,
        "has_submission": project_submissions.exists(),
        "eval_closed": eval_closed,
    }


def projects_eval_view(request, course_slug, project_slug):
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )

    user = request.user
    is_authenticated = user.is_authenticated
    eval_closed = project.state != ProjectState.PEER_REVIEWING.value

    if not is_authenticated:
        context = anonymous_project_eval_context(
            course,
            project,
            eval_closed,
        )
    else:
        context = student_project_eval_context(
            course,
            project,
            user,
            eval_closed,
        )

    return render(request, "projects/eval.html", context)

def criteria_response_answer_indexes(response):
    if response is None:
        return set()

    answers = (response.answer or "").strip().split(",")
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
    enrollment: Optional["Enrollment"] = None,
):
    submission = review.submission_under_evaluation
    accepting_submissions = project_eval_accepting_submissions(project)
    disabled = not accepting_submissions
    responses_by_criteria_id = project_eval_responses_by_criteria_id(review)

    context = {
        "project": project,
        "review": review,
        "submission": submission,
        "criteria_response_pairs": project_eval_criteria_response_pairs(
            review_criteria,
            responses_by_criteria_id,
        ),
        "accepting_submissions": accepting_submissions,
        "disabled": disabled,
        "disable_learning_in_public": (
            project_eval_disable_learning_in_public(enrollment)
        ),
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
        CriteriaResponse.objects.update_or_create(
            review=review,
            criteria=criteria,
            defaults={
                "answer": answers_by_field.get(f"answer_{criteria.id}")
            },
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
    save_project_eval_criteria_responses(
        review,
        review_criteria,
        project_eval_answers_from_post(request.POST),
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


def _redirect_to_projects_eval(course_slug, project_slug):
    return redirect(
        "projects_eval",
        course_slug=course_slug,
        project_slug=project_slug,
    )


def _project_eval_submit_context(request, page: ProjectEvalSubmitPage):
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
    context["voted_submission_ids"] = get_voted_submission_ids(
        request.user,
        page.course,
    )
    project_vote_counts = get_project_vote_counts(request.user, page.course)
    context["vote_limit_reached"] = (
        context["submission"].id not in context["voted_submission_ids"]
        and project_vote_counts.get(context["submission"].project_id, 0)
        >= PROJECT_VOTES_PER_PROJECT
    )
    context["project_votes_per_project"] = PROJECT_VOTES_PER_PROJECT
    return context


def _project_eval_vote_response(request, course_slug, project_slug, review):
    action = request.POST.get("action", "vote")
    update_project_vote(
        request.user,
        review.submission_under_evaluation,
        action=action,
    )
    return redirect(
        "projects_eval_submit",
        course_slug=course_slug,
        project_slug=project_slug,
        review_id=review.id,
    )


def _closed_project_eval_response(
    request,
    page: ProjectEvalSubmitPage,
):
    messages.error(
        request,
        "Peer review form is closed.",
        extra_tags="homework",
    )
    context = _project_eval_submit_context(request, page)
    return render(request, "projects/eval_submit.html", context)


def _redirect_to_project_list(course, project):
    return redirect(
        "project_list",
        course_slug=course.slug,
        project_slug=project.slug,
    )


def _project_eval_student_submission(course, project, user):
    student_submission = ProjectSubmission.objects.filter(
        project=project,
        student=user,
        volunteer_review_only=False,
    ).first()

    if student_submission is not None:
        return student_submission

    enrollment, _ = Enrollment.objects.get_or_create(
        student=user,
        course=course,
    )
    student_submission, _ = ProjectSubmission.objects.get_or_create(
        project=project,
        student=user,
        volunteer_review_only=True,
        defaults={
            "enrollment": enrollment,
            "github_link": (
                "https://github.com/DataTalksClub/"
                "course-management-platform"
            ),
            "commit_id": "volunteer",
        },
    )
    return student_submission


def _submission_under_project_evaluation(project, submission_id):
    return ProjectSubmission.objects.get(
        id=submission_id,
        project=project,
        volunteer_review_only=False,
    )


def _create_optional_peer_review(
    student_submission,
    submission_under_evaluation,
):
    PeerReview.objects.get_or_create(
        submission_under_evaluation=submission_under_evaluation,
        reviewer=student_submission,
        optional=True,
    )


def _projects_eval_submit_post_response(
    request,
    page: ProjectEvalSubmitPage,
):
    if request.POST.get("form_action") == "vote":
        return _project_eval_vote_response(
            request,
            page.course.slug,
            page.project.slug,
            page.review,
        )

    if page.project.state != ProjectState.PEER_REVIEWING.value:
        return _closed_project_eval_response(
            request,
            page,
        )

    project_eval_post_submission(
        request,
        page.project,
        page.review,
        page.review_criteria,
    )
    return _redirect_to_projects_eval(page.course.slug, page.project.slug)


def _project_eval_submit_page(
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

    # check if the submission belongs to the student
    if review.reviewer.student != request.user:
        messages.error(
            request,
            "You are not allowed to evaluate this submission, choose a different one.",
            extra_tags="homework",
        )
        return _redirect_to_projects_eval(course_slug, project_slug)

    page = _project_eval_submit_page(course_slug, project_slug, review)

    if request.method == "POST":
        return _projects_eval_submit_post_response(
            request,
            page,
        )

    context = _project_eval_submit_context(
        request,
        page,
    )

    return render(request, "projects/eval_submit.html", context)


@login_required
def projects_eval_add(
    request, course_slug, project_slug, submission_id
):
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )
    student_submission = _project_eval_student_submission(
        course,
        project,
        request.user,
    )

    if student_submission.id == submission_id:
        return _redirect_to_project_list(course, project)

    _create_optional_peer_review(
        student_submission,
        _submission_under_project_evaluation(project, submission_id),
    )

    return _redirect_to_project_list(course, project)


@login_required
def projects_eval_delete(request, course_slug, project_slug, review_id):
    project = get_object_or_404(
        Project, course__slug=course_slug, slug=project_slug
    )

    user = request.user

    student_submission = get_object_or_404(
        ProjectSubmission,
        project=project,
        student=user,
    )

    PeerReview.objects.filter(
        id=review_id,
        reviewer=student_submission,
        optional=True,
    ).delete()

    return redirect(
        "projects_eval",
        course_slug=course_slug,
        project_slug=project_slug,
    )
