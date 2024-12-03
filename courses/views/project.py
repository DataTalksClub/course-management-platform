import logging

from typing import Iterable

from django.http import HttpRequest

from django.contrib import messages
from django.utils import timezone
from django.shortcuts import render, get_object_or_404, redirect
from django.core.exceptions import ValidationError
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
    ProjectEvaluationScore,
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
        project_submission = ProjectSubmission(
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
            project_submission.time_spent = tryparsefloat(time_spent)

    if project.problems_comments_field:
        problems_comments = request.POST.get("problems_comments", "")
        project_submission.problems_comments = problems_comments.strip()

    if project.faq_contribution_field:
        faq_contribution = request.POST.get("faq_contribution", "")
        project_submission.faq_contribution = faq_contribution.strip()

    project_submission.full_clean()
    project_submission.save()

    messages.success(
        request,
        "Thank you for submitting your project, it is now saved. You can update your submission at any point before the due date.",
        extra_tags="homework",
    )


def project_delete_submission(request: HttpRequest, project: Project) -> None:
    user = request.user

    project_submission = ProjectSubmission.objects.filter(
        project=project, student=request.user
    ).first()

    if project_submission:
        project_submission.delete()

    messages.success(
        request,
        "Your project submission is deleted. You can still make a new submission if you want.",
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

        if 'action' in request.POST and request.POST['action'] == 'delete':
            project_delete_submission(request, project)
        else:
            try:
                project_submit_post(request, project)
            except ValidationError as e:
                for message in e.messages:
                    messages.error(
                        request,
                        f"Failed to submit the project: {message}",
                        extra_tags="alert-danger",
                    )

        return redirect(
            "project",
            course_slug=course.slug,
            project_slug=project.slug,
        )

    project_submission = None
    ceritificate_name = None

    if is_authenticated:
        project_submission = ProjectSubmission.objects.filter(
            project=project, student=request.user
        ).first()

        enrollment, _ = Enrollment.objects.get_or_create(
            student=user,
            course=course,
        )

        ceritificate_name = (
            enrollment.certificate_name or enrollment.display_name
        )

    disabled = not accepting_submissions

    context = {
        "course": course,
        "project": project,
        "submission": project_submission,
        "is_authenticated": is_authenticated,
        "disabled": disabled,
        "accepting_submissions": accepting_submissions,
        "ceritificate_name": ceritificate_name,
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
    ).order_by("optional")

    number_of_completed_evaluation = 0

    for review in reviews:
        if review.optional:
            continue
        if review.state == PeerReviewState.SUBMITTED.value:
            number_of_completed_evaluation += 1

    context = {
        "course": course,
        "project": project,
        "reviews": reviews,
        "is_authenticated": True,
        "number_of_completed_evaluation": number_of_completed_evaluation,
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
            "is_authenticated": False,
        }

        return render(request, "projects/results.html", context)

    submission = ProjectSubmission.objects.filter(
        project=project, student=user
    ).first()

    scores = list(
        ProjectEvaluationScore.objects.filter(submission=submission)
        .order_by("review_criteria__id")
        .prefetch_related("review_criteria")
    )

    feedback = list(
        PeerReview.objects.filter(
            submission_under_evaluation=submission,
            state=PeerReviewState.SUBMITTED.value,
            note_to_peer__isnull=False,
            note_to_peer__gt="",
        )
    )

    context = {
        "course": course,
        "project": project,
        "submission": submission,
        "scores": scores,
        "feedback": feedback,
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
        project.state == ProjectState.PEER_REVIEWING.value
    )

    disabled = not accepting_submissions

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
        "disabled": disabled,
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
    review = get_object_or_404(PeerReview, id=review_id)

    # check if the submission belongs to the student
    if review.reviewer.student != request.user:
        messages.error(
            request,
            "You are not allowed to evaluate this submission, choose a different one.",
            extra_tags="homework",
        )
        return redirect(
            "projects_eval",
            course_slug=course_slug,
            project_slug=project_slug,
        )

    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, slug=project_slug, course=course
    )

    review_criteria = ReviewCriteria.objects.filter(
        course=course
    ).order_by("id")

    if request.method == "POST":
        project_eval_post_submission(
            request, project, review, review_criteria
        )

        return redirect(
            "projects_eval",
            course_slug=course_slug,
            project_slug=project_slug
        )

    context = project_eval_build_context(
        project, review, review_criteria
    )
    context["course"] = course

    return render(request, "projects/eval_submit.html", context)


@login_required
def projects_eval_add(
    request, course_slug, project_slug, submission_id
):
    user = request.user
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )
    student_submission = ProjectSubmission.objects.get(
        project=project, student=user
    )

    if student_submission.id == submission_id:
        # don't allow self-evaluation
        return redirect(
            "project_list",
            course_slug=course.slug,
            project_slug=project.slug,
        )

    submission_under_evaluation = ProjectSubmission.objects.get(
        id=submission_id
    )

    review, created = PeerReview.objects.get_or_create(
        submission_under_evaluation=submission_under_evaluation,
        reviewer=student_submission,
        optional=True,
    )

    return redirect(
        "project_list",
        course_slug=course.slug,
        project_slug=project.slug,
    )


@login_required
def projects_eval_delete(request, course_slug, project_slug, review_id):
    project = get_object_or_404(
        Project, course__slug=course_slug, slug=project_slug
    )

    user = request.user

    student_submission = get_object_or_404(
        ProjectSubmission, project=project, student=user
    )

    PeerReview.objects.filter(
        id=review_id,
        reviewer=student_submission,
        optional=True,
    ).delete()

    return redirect(
        "project_list",
        course_slug=course_slug,
        project_slug=project_slug,
    )


def projects_list_view(request, course_slug, project_slug):
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )

    submissions = ProjectSubmission.objects.filter(project=project)

    if project.state == ProjectState.COMPLETED.value:
        submissions = submissions.order_by('-project_score')

    user = request.user
    is_authenticated = user.is_authenticated

    review_ids = {}
    own_submissions = set()

    if is_authenticated:
        student_submissions = ProjectSubmission.objects.filter(
            project=project, student=user
        )

        own_submissions = set(student_submissions.values_list("id", flat=True))

        reviews = PeerReview.objects.filter(
            reviewer__in=student_submissions,
            submission_under_evaluation__project=project,
        )

        for review in reviews:
            eval_id = review.submission_under_evaluation_id
            review_ids[eval_id] = review


    for submission in submissions:
        if submission.id in review_ids:
            submission.to_evaluate = True
            submission.review = review_ids[submission.id]
        else:
            submission.to_evaluate = False

        submission.own = submission.id in own_submissions

    context = {
        "course": course,
        "project": project,
        "submissions": submissions,
        "is_authenticated": is_authenticated,
    }

    return render(request, "projects/list.html", context)
