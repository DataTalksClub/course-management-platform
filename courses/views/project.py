import logging

from typing import Iterable, Optional
from collections import defaultdict

from django.http import HttpRequest, JsonResponse

from django.contrib import messages
from django.utils import timezone
from django.shortcuts import render, get_object_or_404, redirect
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.db import transaction
from django.urls import reverse

from course_management import email_templates
from course_management.datamailer import (
    send_transactional_email,
    sync_project_submission_to_datamailer,
)
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

from courses.scoring import calculate_project_statistics
from courses.views.url_utils import absolute_url_with_fallback
from courses.votes import (
    PROJECT_VOTES_PER_PROJECT,
    get_project_vote_counts,
    get_voted_submission_ids,
    update_project_vote,
)


from .homework import (
    build_account_settings_url,
    clean_learning_in_public_links,
    format_hours,
    format_submission_lines,
    request_base_url,
    tryparsefloat,
)

logger = logging.getLogger(__name__)
PROJECT_SUBMISSIONS_PAGE_SIZE = 25


def paginate_project_submissions(request, submissions):
    paginator = Paginator(submissions, PROJECT_SUBMISSIONS_PAGE_SIZE)
    return paginator.get_page(request.GET.get("page"))


def project_submission_fields(
    project: Project,
    submission: ProjectSubmission,
) -> list[dict]:
    fields = [
        {
            "key": "github_link",
            "label": "GitHub repository",
            "value": submission.github_link or "",
        },
        {
            "key": "commit_id",
            "label": "Commit ID",
            "value": submission.commit_id or "",
        },
    ]

    if project.learning_in_public_cap_project > 0:
        links = submission.learning_in_public_links or []
        fields.append(
            {
                "key": "learning_in_public_links",
                "label": "Learning in public links",
                "value": "\n".join(links),
                "values": links,
            }
        )

    if project.time_spent_project_field:
        fields.append(
            {
                "key": "time_spent",
                "label": "Time spent on project",
                "value": format_hours(submission.time_spent),
            }
        )

    if project.problems_comments_field:
        fields.append(
            {
                "key": "problems_comments",
                "label": "Problems, comments, or feedback",
                "value": submission.problems_comments or "",
            }
        )

    if project.faq_contribution_field:
        fields.append(
            {
                "key": "faq_contribution_url",
                "label": "FAQ contribution URL",
                "value": submission.faq_contribution_url or "",
            }
        )

    return fields


def project_confirmation_context(
    course: Course,
    project: Project,
    submission: ProjectSubmission,
    update_url: str,
    profile_url: str,
) -> dict:
    submission_fields = project_submission_fields(project, submission)
    submitted_fields_text = format_submission_lines(submission_fields)

    return {
        "course_slug": course.slug,
        "course_title": course.title,
        "project_slug": project.slug,
        "project_title": project.title,
        "project_due_at": project.submission_due_date.isoformat(),
        "submission_id": submission.id,
        "submitted_at": submission.submitted_at.isoformat(),
        "update_url": update_url,
        "profile_url": profile_url,
        "update_link_text": "Update your submission",
        "notification_category": "homework and project submissions",
        "notification_footer": (
            "You are receiving this because homework and project "
            "submission emails are enabled in your profile."
        ),
        "notification_footer_text": (
            "If you don't want to receive these emails, you can turn "
            "off homework and project submission emails in your "
            f"profile: {profile_url}"
        ),
        "email_subject": f"Project submission saved: {project.title}",
        "email_preview": (
            "Your project submission was saved. Review what you "
            "submitted and update it while the project is open."
        ),
        "intro_text": (
            f"Your project submission for {project.title} in "
            f"{course.title} was saved."
        ),
        "update_text": (
            "You can update your submission while the project "
            f"is open: {update_url}"
        ),
        "submission_fields": submission_fields,
        "submitted_fields_text": submitted_fields_text,
        "submission_summary_text": submitted_fields_text,
    }


def build_project_update_url(
    request: HttpRequest,
    course: Course,
    project: Project,
) -> str:
    path = reverse(
        "project",
        kwargs={
            "course_slug": course.slug,
            "project_slug": project.slug,
        },
    )
    return absolute_url_with_fallback(request, path, label="project")


def send_project_confirmation_email(
    user: User,
    course: Course,
    project: Project,
    submission: ProjectSubmission,
    update_url: str,
) -> None:
    if not user.email:
        return

    context = project_confirmation_context(
        course=course,
        project=project,
        submission=submission,
        update_url=update_url,
        profile_url=build_account_settings_url(
            request_base_url(update_url)
        ),
    )

    send_transactional_email(
        {
            "email": user.email,
            "template_key": (
                email_templates.PROJECT_SUBMISSION_CONFIRMATION
            ),
            "category_tag": "submission-results",
            "idempotency_key": (
                f"project-submission:{submission.id}:"
                f"{submission.submitted_at.isoformat()}"
            ),
            "context": context,
            "metadata": {
                "source": "course-management-platform",
                "event": "project_submission",
                "course_slug": course.slug,
                "project_slug": project.slug,
                "submission_id": submission.id,
            },
        }
    )


def project_submission_from_post(
    request: HttpRequest, project: Project
) -> ProjectSubmission:
    user = request.user

    project_submission = ProjectSubmission.objects.filter(
        project=project,
        student=request.user,
        volunteer_review_only=False,
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

    # Certificate name is a user-level account setting.
    certificate_name = request.POST.get("certificate_name", "").strip()
    if certificate_name:
        user.certificate_name = certificate_name
        user.save(update_fields=["certificate_name"])

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
        faq_contribution_url = request.POST.get(
            "faq_contribution_url", ""
        )
        project_submission.faq_contribution_url = (
            faq_contribution_url.strip()
        )

    return project_submission


def project_submit_post(request: HttpRequest, project: Project) -> None:
    project_submission = project_submission_from_post(request, project)
    project_submission.full_clean()
    project_submission.save()
    update_url = build_project_update_url(
        request, project.course, project
    )
    transaction.on_commit(
        lambda: sync_project_submission_to_datamailer(
            project_submission
        )
    )
    transaction.on_commit(
        lambda: send_project_confirmation_email(
            user=request.user,
            course=project.course,
            project=project,
            submission=project_submission,
            update_url=update_url,
        )
    )

    messages.success(
        request,
        "Thank you for submitting your project, it is now saved. You can update your submission at any point before the due date.",
        extra_tags="homework",
    )


def project_delete_submission(
    request: HttpRequest, project: Project
) -> None:
    project_submission = ProjectSubmission.objects.filter(
        project=project,
        student=request.user,
        volunteer_review_only=False,
    ).first()

    if project_submission:
        project_submission.delete()

    messages.success(
        request,
        "Your project submission is deleted. You can still make a new submission if you want.",
        extra_tags="homework",
    )


def project_build_context(
    request: HttpRequest, course: Course, project: Project
) -> dict:
    user = request.user
    is_authenticated = user.is_authenticated

    accepting_submissions = (
        project.state == ProjectState.COLLECTING_SUBMISSIONS.value
    )

    project_submission = None
    enrollment = None
    ceritificate_name = None

    if is_authenticated:
        project_submission = ProjectSubmission.objects.filter(
            project=project,
            student=user,
            volunteer_review_only=False,
        ).first()

        enrollment, _ = Enrollment.objects.get_or_create(
            student=user,
            course=course,
        )

        ceritificate_name = (
            user.certificate_name or enrollment.display_name
        )

    disabled = not accepting_submissions

    return {
        "course": course,
        "project": project,
        "submission": project_submission,
        "is_authenticated": is_authenticated,
        "disabled": disabled,
        "accepting_submissions": accepting_submissions,
        "ceritificate_name": ceritificate_name,
        "disable_learning_in_public": (
            enrollment.disable_learning_in_public
            if enrollment
            else False
        ),
    }


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
                "Project submission form is closed.",
                extra_tags="homework",
            )
            context = project_build_context(request, course, project)
            return render(request, "projects/project.html", context)

        if (
            "action" in request.POST
            and request.POST["action"] == "delete"
        ):
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
                context = project_build_context(
                    request, course, project
                )
                context["submission"] = project_submission_from_post(
                    request, project
                )
                return render(request, "projects/project.html", context)

        return redirect(
            "project",
            course_slug=course.slug,
            project_slug=project.slug,
        )

    context = project_build_context(request, course, project)

    return render(request, "projects/project.html", context)


def projects_eval_view(request, course_slug, project_slug):
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )

    user = request.user
    is_authenticated = user.is_authenticated
    eval_closed = project.state != ProjectState.PEER_REVIEWING.value

    if not is_authenticated:
        context = {
            "course": course,
            "project": project,
            "is_authenticated": False,
            "eval_closed": eval_closed,
        }

        return render(request, "projects/eval.html", context)

    student_submissions = ProjectSubmission.objects.filter(
        project=project, student=user
    )

    project_submissions = student_submissions.filter(
        volunteer_review_only=False,
    )
    has_submission = project_submissions.exists()

    reviews = PeerReview.objects.filter(
        reviewer__in=student_submissions,
        submission_under_evaluation__project=project,
    ).order_by("optional")
    assigned_reviews = []
    selected_reviews = []

    number_of_completed_evaluation = 0

    for review in reviews:
        if review.optional:
            selected_reviews.append(review)
            continue
        assigned_reviews.append(review)
        if review.state == PeerReviewState.SUBMITTED.value:
            number_of_completed_evaluation += 1

    context = {
        "course": course,
        "project": project,
        "reviews": reviews,
        "assigned_reviews": assigned_reviews,
        "selected_reviews": selected_reviews,
        "is_authenticated": True,
        "number_of_completed_evaluation": number_of_completed_evaluation,
        "has_submission": has_submission,
        "eval_closed": eval_closed,
    }

    return render(request, "projects/eval.html", context)


def answer_option_indexes(answer: str) -> list[int]:
    if not answer:
        return []

    indexes = []
    for value in answer.split(","):
        value = value.strip()
        if value:
            indexes.append(int(value) - 1)
    return indexes


def annotate_scores_with_option_votes(
    submission: ProjectSubmission,
    scores: list[ProjectEvaluationScore],
) -> None:
    criteria_ids = [score.review_criteria_id for score in scores]
    responses = CriteriaResponse.objects.filter(
        review__submission_under_evaluation=submission,
        review__state=PeerReviewState.SUBMITTED.value,
        criteria_id__in=criteria_ids,
    )

    votes_by_criteria = defaultdict(lambda: defaultdict(int))
    for response in responses:
        for option_index in answer_option_indexes(response.answer):
            votes_by_criteria[response.criteria_id][option_index] += 1

    for score in scores:
        option_votes = votes_by_criteria[score.review_criteria_id]
        score.option_vote_counts = [
            {
                **option,
                "votes": option_votes[index],
            }
            for index, option in enumerate(
                score.review_criteria.options
            )
        ]


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
        project=project,
        student=user,
        volunteer_review_only=False,
    ).first()

    scores = list(
        ProjectEvaluationScore.objects.filter(submission=submission)
        .order_by("review_criteria__id")
        .prefetch_related("review_criteria")
    )
    annotate_scores_with_option_votes(submission, scores)

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
    enrollment: Optional["Enrollment"] = None,
):
    submission = review.submission_under_evaluation

    accepting_submissions = (
        project.state == ProjectState.PEER_REVIEWING.value
    )

    disabled = not accepting_submissions

    # Check if learning in public is disabled for this enrollment
    disable_learning_in_public = (
        enrollment.disable_learning_in_public if enrollment else False
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
        "disabled": disabled,
        "disable_learning_in_public": disable_learning_in_public,
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

    # Get the enrollment for the reviewer
    enrollment, _ = Enrollment.objects.get_or_create(
        student=request.user,
        course=course,
    )

    if request.method == "POST":
        if request.POST.get("form_action") == "vote":
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

        if project.state != ProjectState.PEER_REVIEWING.value:
            messages.error(
                request,
                "Peer review form is closed.",
                extra_tags="homework",
            )
            context = project_eval_build_context(
                project, review, review_criteria, enrollment
            )
            context["course"] = course
            return render(request, "projects/eval_submit.html", context)

        project_eval_post_submission(
            request, project, review, review_criteria
        )

        return redirect(
            "projects_eval",
            course_slug=course_slug,
            project_slug=project_slug,
        )

    context = project_eval_build_context(
        project, review, review_criteria, enrollment
    )
    context["course"] = course
    context["voted_submission_ids"] = get_voted_submission_ids(
        request.user,
        course,
    )
    project_vote_counts = get_project_vote_counts(request.user, course)
    context["vote_limit_reached"] = (
        context["submission"].id not in context["voted_submission_ids"]
        and project_vote_counts.get(context["submission"].project_id, 0)
        >= PROJECT_VOTES_PER_PROJECT
    )
    context["project_votes_per_project"] = PROJECT_VOTES_PER_PROJECT

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
    student_submission = ProjectSubmission.objects.filter(
        project=project,
        student=user,
        volunteer_review_only=False,
    ).first()

    if student_submission is None:
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

    if student_submission.id == submission_id:
        # don't allow self-evaluation
        return redirect(
            "project_list",
            course_slug=course.slug,
            project_slug=project.slug,
        )

    submission_under_evaluation = ProjectSubmission.objects.get(
        id=submission_id,
        project=project,
        volunteer_review_only=False,
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


def _project_vote_response(request, course, project):
    """Handle a POST vote on a project submission (HTML redirect or AJAX JSON)."""
    if not request.user.is_authenticated:
        return redirect("login")

    submission_id = request.POST.get("submission_id")
    action = request.POST.get("action", "vote")
    submission = get_object_or_404(
        ProjectSubmission.objects.select_related("project"),
        id=submission_id,
        project=project,
        volunteer_review_only=False,
    )
    update_project_vote(request.user, submission, action=action)

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        voted_submission_ids = get_voted_submission_ids(request.user, course)
        project_vote_counts = get_project_vote_counts(request.user, course)
        project_vote_count = project_vote_counts.get(project.id, 0)
        votes_left = max(PROJECT_VOTES_PER_PROJECT - project_vote_count, 0)
        vote_count = (
            ProjectSubmission.objects.filter(id=submission.id)
            .annotate(vote_count=Count("votes"))
            .values_list("vote_count", flat=True)
            .get()
        )

        return JsonResponse(
            {
                "submission_id": submission.id,
                "vote_count": vote_count,
                "voted": submission.id in voted_submission_ids,
                "voted_submission_ids": list(voted_submission_ids),
                "votes_left": votes_left,
                "vote_limit_reached": (
                    project_vote_count >= PROJECT_VOTES_PER_PROJECT
                ),
            }
        )

    return redirect(
        "project_list",
        course_slug=course.slug,
        project_slug=project.slug,
    )


def _decorate_project_submissions(
    submissions_list,
    *,
    project,
    is_authenticated,
    review_ids,
    own_submissions,
    voted_submission_ids,
    project_vote_counts,
    has_assigned_reviews,
):
    """Attach per-submission display flags (ordering, ownership, review group)."""
    in_peer_review = (
        is_authenticated
        and project.state == ProjectState.PEER_REVIEWING.value
    )

    for order, submission in enumerate(submissions_list):
        submission.list_order = order
        if submission.id in review_ids:
            submission.to_evaluate = True
            submission.review = review_ids[submission.id]
        else:
            submission.to_evaluate = False

        submission.own = submission.id in own_submissions
        submission.vote_limit_reached = (
            submission.id not in voted_submission_ids
            and project_vote_counts.get(project.id, 0)
            >= PROJECT_VOTES_PER_PROJECT
        )
        submission.group_order = 1
        submission.group_label = None

        if in_peer_review:
            if submission.to_evaluate and not submission.review.optional:
                submission.group_order = 0
                submission.group_label = "Assigned reviews"
            else:
                submission.group_order = 1
                if has_assigned_reviews:
                    submission.group_label = "Other submissions"


def _project_submissions_queryset(project):
    submissions = (
        ProjectSubmission.objects.filter(
            project=project,
            volunteer_review_only=False,
        )
        .select_related("enrollment")
        .annotate(vote_count=Count("votes"))
    )

    if project.state == ProjectState.COMPLETED.value:
        return submissions.order_by("-project_score")

    return submissions.order_by("-submitted_at")


def _project_viewer_state(project, course, user):
    is_authenticated = user.is_authenticated
    voted_submission_ids = get_voted_submission_ids(user, course)
    project_vote_counts = get_project_vote_counts(user, course)
    project_vote_count = project_vote_counts.get(project.id, 0)

    state = {
        "is_authenticated": is_authenticated,
        "review_ids": {},
        "own_submissions": set(),
        "has_submission": False,
        "voted_submission_ids": voted_submission_ids,
        "project_vote_counts": project_vote_counts,
        "project_votes_left": max(
            PROJECT_VOTES_PER_PROJECT - project_vote_count,
            0,
        ),
        "has_assigned_reviews": False,
    }

    if not is_authenticated:
        return state

    student_submissions = ProjectSubmission.objects.filter(
        project=project, student=user
    )
    project_submissions = student_submissions.filter(
        volunteer_review_only=False,
    )
    state["own_submissions"] = set(
        project_submissions.values_list("id", flat=True)
    )
    state["has_submission"] = len(state["own_submissions"]) > 0

    reviews = PeerReview.objects.filter(
        reviewer__in=student_submissions,
        submission_under_evaluation__project=project,
    )
    for review in reviews:
        eval_id = review.submission_under_evaluation_id
        state["review_ids"][eval_id] = review
        if not review.optional:
            state["has_assigned_reviews"] = True

    return state


def _sort_project_submissions_for_view(
    submissions_list,
    *,
    project,
    is_authenticated,
):
    if (
        is_authenticated
        and project.state == ProjectState.PEER_REVIEWING.value
    ):
        submissions_list.sort(
            key=lambda submission: (
                submission.group_order,
                submission.list_order,
            )
        )


def _apply_project_group_headings(submissions_page):
    previous_group_label = None
    for submission in submissions_page.object_list:
        submission.group_heading = None
        if (
            submission.group_label
            and submission.group_label != previous_group_label
        ):
            submission.group_heading = submission.group_label
        previous_group_label = submission.group_label


def projects_list_view(request, course_slug, project_slug):
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )

    if request.method == "POST":
        return _project_vote_response(request, course, project)

    user = request.user
    viewer_state = _project_viewer_state(project, course, user)
    submissions_list = list(_project_submissions_queryset(project))
    _decorate_project_submissions(
        submissions_list,
        project=project,
        is_authenticated=viewer_state["is_authenticated"],
        review_ids=viewer_state["review_ids"],
        own_submissions=viewer_state["own_submissions"],
        voted_submission_ids=viewer_state["voted_submission_ids"],
        project_vote_counts=viewer_state["project_vote_counts"],
        has_assigned_reviews=viewer_state["has_assigned_reviews"],
    )
    _sort_project_submissions_for_view(
        submissions_list,
        project=project,
        is_authenticated=viewer_state["is_authenticated"],
    )

    submissions_page = paginate_project_submissions(
        request, submissions_list
    )
    _apply_project_group_headings(submissions_page)

    context = {
        "course": course,
        "project": project,
        "submissions": submissions_page.object_list,
        "submissions_page": submissions_page,
        "page_range": submissions_page.paginator.get_elided_page_range(
            submissions_page.number
        ),
        "is_authenticated": viewer_state["is_authenticated"],
        "has_submission": viewer_state["has_submission"],
        "voted_submission_ids": viewer_state["voted_submission_ids"],
        "project_votes_per_project": PROJECT_VOTES_PER_PROJECT,
        "project_votes_left": viewer_state["project_votes_left"],
    }

    return render(request, "projects/list.html", context)


def project_statistics(request, course_slug, project_slug):
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )

    if project.state != ProjectState.COMPLETED.value:
        messages.error(
            request,
            "This project is not completed yet, so there are no available statistics.",
            extra_tags="project",
        )
        return redirect(
            "project",
            course_slug=course.slug,
            project_slug=project.slug,
        )

    stats = calculate_project_statistics(project, force=False)

    context = {
        "course": course,
        "project": project,
        "stats": stats,
    }

    return render(request, "projects/stats.html", context)


def project_submissions(request, course_slug, project_slug):
    # Check if user is staff - if not, redirect to project view with error
    if not request.user.is_authenticated or not request.user.is_staff:
        messages.error(
            request,
            "You do not have permission to view this page.",
            extra_tags="project",
        )
        return redirect(
            "project",
            course_slug=course_slug,
            project_slug=project_slug,
        )

    # Staff users: redirect to cadmin view
    return redirect(
        "cadmin_project_submissions",
        course_slug=course_slug,
        project_slug=project_slug,
    )
