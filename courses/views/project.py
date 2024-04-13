import logging

from typing import Iterable

from django.http import HttpRequest

from django.contrib import messages
from django.utils import timezone
from django.shortcuts import render, get_object_or_404, redirect

from django.contrib.auth.decorators import login_required

from courses.models import (
    Course,
    Enrollment,
    Project,
    ProjectSubmission,
    ProjectState,
    PeerReview,
    PeerReviewState,
    ReviewCriteria,
    CriteriaResponse,
    User,
)


from .homework import tryparsefloat, clean_learning_in_public_links

logger = logging.getLogger(__name__)


def project_submit_post(request: HttpRequest, project: Project) -> None:
    user = request.user

    project_submission = ProjectSubmission.objects.filter(
        project=project, student=request.user
    ).first()

    if project_submission:
        enrollment = project_submission.enrollment
        project_submission.submitted_at = timezone.now()
    else:
        enrollment, _ = Enrollment.objects.get_or_create(
            student=user,
            course=project.course,
        )
        project_submission = ProjectSubmission.objects.create(
            project=project,
            student=user,
            enrollment=enrollment,
        )

    project_submission.github_link = request.POST.get("github_link")
    project_submission.commit_id = request.POST.get("commit_id")

    if project.learning_in_public_cap_project > 0:
        links = request.POST.getlist("learning_in_public_links[]")
        cleaned_links = clean_learning_in_public_links(
            links, project.learning_in_public_cap_project
        )
        project_submission.learning_in_public_links = cleaned_links

    if project.time_spent_project_field:
        time_spent = request.POST.get("time_spent")
        if time_spent is not None and time_spent != "":
            project_submission.time_spent = tryparsefloat(
                time_spent
            )

    if project.problems_comments_field:
        problems_comments = request.POST.get(
            "problems_comments", ""
        )
        project_submission.problems_comments = (
            problems_comments.strip()
        )

    if project.faq_contribution_field:
        faq_contribution = request.POST.get("faq_contribution", "")
        project_submission.faq_contribution = (
            faq_contribution.strip()
        )

    project_submission.save()

    messages.success(
        request,
        "Thank you for submitting your project, it is now saved. You can update your submission at any point before the due date.",
        extra_tags="homework",
    )


def project_view(request, course_slug, project_slug):
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )

    user = request.user
    is_authenticated = user.is_authenticated

    accepting_submissions = (
        project.state == ProjectState.COLLECTING_SUBMISSIONS.value
    )

    if request.method == "POST":
        if not is_authenticated:
            messages.error(
                request,
                "You need to be logged in to submit a project",
                extra_tags="homework",
            )
            return redirect(
                "project",
                course_slug=course.slug,
                project_slug=project.slug,
            )

        if not accepting_submissions:
            messages.error(
                request,
                "This project is no longer accepting submissions",
                extra_tags="homework",
            )
            return redirect(
                "project",
                course_slug=course.slug,
                project_slug=project.slug,
            )

        project_submit_post(request, project)

        return redirect(
            "project",
            course_slug=course.slug,
            project_slug=project.slug,
        )

    project_submission = None

    if is_authenticated:
        project_submission = ProjectSubmission.objects.filter(
            project=project, student=request.user
        ).first()

    disabled = not accepting_submissions

    context = {
        "course": course,
        "project": project,
        "submission": project_submission,
        "is_authenticated": is_authenticated,
        "disabled": disabled,
        "accepting_submissions": accepting_submissions,
    }

    return render(request, "projects/project.html", context)


def projects_eval_view(request, course_slug, project_slug):
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )

    user = request.user
    is_authenticated = user.is_authenticated

    if not is_authenticated:
        context = {
            "course": course,
            "project": project,
            "is_authenticated": False,
        }

        return render(request, "projects/eval.html", context)

    student_submissions = ProjectSubmission.objects.filter(
        project=project, student=user
    )

    reviews = PeerReview.objects.filter(
        reviewer__in=student_submissions,
        submission_under_evaluation__project=project,
    )

    context = {
        "course": course,
        "project": project,
        "reviews": reviews,
        "is_authenticated": True
    }

    return render(request, "projects/eval.html", context)


def project_results(request, course_slug, project_slug):
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )

    user = request.user
    is_authenticated = user.is_authenticated

    if not is_authenticated:
        context = {
            "course": course,
            "project": project,
            "submission": None,
            "is_authenticated": False,
        }

        return render(request, "projects/results.html", context)

    submission = ProjectSubmission.objects.filter(
        project=project, student=user
    ).first()

    context = {
        "course": course,
        "project": project,
        "submission": submission,
        "is_authenticated": True,
    }

    return render(request, "projects/results.html", context)





def project_eval_build_context(
    project: Project,
    review: PeerReview,
    review_criteria: Iterable[ReviewCriteria],
):
    submission = review.submission_under_evaluation

    accepting_submissions = (
        project.state == ProjectState.COLLECTING_SUBMISSIONS.value
    )

    review_responses = review.get_criteria_responses()

    responses_by_criteria_id = {
        r.criteria.id: r for r in review_responses
    }

    criteria_response_pairs = []

    for criteria in review_criteria:
        response = responses_by_criteria_id.get(criteria.id)

        if response is None:
            answer_int = set()
        else:
            answers = (response.answer or "").strip().split(",")
            answer_int = {int(a) for a in answers if a}

        index = 1
        for option in criteria.options:
            option["index"] = index
            option["is_selected"] = index in answer_int
            index = index + 1

        criteria_response_pairs.append((criteria, response))

    context = {
        "project": project,
        "review": review,
        "submission": submission,
        "criteria_response_pairs": criteria_response_pairs,
        "accepting_submissions": accepting_submissions,
    }

    return context


def project_eval_post_submission(
    request: HttpRequest,
    project: Project,
    review: PeerReview,
    review_criteria: Iterable[ReviewCriteria],
) -> None:
    answers_dict = {}

    for answer_id, answer in request.POST.lists():
        if not answer_id.startswith("answer_"):
            continue
        answer = [a.strip() for a in answer]
        answers_dict[answer_id] = ",".join(answer)

    for criteria in review_criteria:
        answer_text = answers_dict.get(f"answer_{criteria.id}")

        values = {"answer": answer_text}

        CriteriaResponse.objects.update_or_create(
            review=review,
            criteria=criteria,
            defaults=values,
        )

    if project.learning_in_public_cap_review > 0:
        links = request.POST.getlist("learning_in_public_links[]")
        cleaned_links = clean_learning_in_public_links(
            links, project.learning_in_public_cap_review
        )
        review.learning_in_public_links = cleaned_links

    if project.time_spent_evaluation_field:
        time_spent_reviewing = request.POST.get("time_spent_reviewing")
        if (
            time_spent_reviewing is not None
            and time_spent_reviewing != ""
        ):
            review.time_spent_reviewing = float(time_spent_reviewing)

    if project.problems_comments_field:
        problems_comments = request.POST.get("problems_comments", "")
        review.problems_comments = problems_comments.strip()

    note_to_peer = request.POST.get("note_to_peer", "")
    review.note_to_peer = note_to_peer.strip()

    review.submitted_at = timezone.now()
    review.state = PeerReviewState.SUBMITTED.value
    review.save()

    messages.success(
        request,
        "Thank you for submitting your evaluation, it is now saved. You can update it at any point.",
        extra_tags="homework",
    )


@login_required
def projects_eval_submit(request, course_slug, project_slug, review_id):
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, slug=project_slug, course=course
    )
    review = get_object_or_404(PeerReview, id=review_id)
    review_criteria = ReviewCriteria.objects.filter(course=course)

    if request.method == "POST":
        project_eval_post_submission(
            request, project, review, review_criteria
        )

        return redirect(
            "projects_eval_submit",
            course_slug=course_slug,
            project_slug=project_slug,
            review_id=review_id,
        )

    context = project_eval_build_context(
        project, review, review_criteria
    )
    context["course"] = course

    return render(request, "projects/eval_submit.html", context)
