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


def project_repository_submission_field(
    submission: ProjectSubmission,
) -> dict:
    return {
        "key": "github_link",
        "label": "GitHub repository",
        "value": submission.github_link or "",
    }


def project_commit_submission_field(
    submission: ProjectSubmission,
) -> dict:
    return {
        "key": "commit_id",
        "label": "Commit ID",
        "value": submission.commit_id or "",
    }


def project_learning_in_public_submission_field(
    project: Project,
    submission: ProjectSubmission,
) -> dict | None:
    if project.learning_in_public_cap_project <= 0:
        return None

    links = submission.learning_in_public_links or []
    return {
        "key": "learning_in_public_links",
        "label": "Learning in public links",
        "value": "\n".join(links),
        "values": links,
    }


def project_time_submission_field(
    project: Project,
    submission: ProjectSubmission,
) -> dict | None:
    if not project.time_spent_project_field:
        return None

    return {
        "key": "time_spent",
        "label": "Time spent on project",
        "value": format_hours(submission.time_spent),
    }


def project_problems_comments_submission_field(
    project: Project,
    submission: ProjectSubmission,
) -> dict | None:
    if not project.problems_comments_field:
        return None

    return {
        "key": "problems_comments",
        "label": "Problems, comments, or feedback",
        "value": submission.problems_comments or "",
    }


def project_faq_contribution_submission_field(
    project: Project,
    submission: ProjectSubmission,
) -> dict | None:
    if not project.faq_contribution_field:
        return None

    return {
        "key": "faq_contribution_url",
        "label": "FAQ contribution URL",
        "value": submission.faq_contribution_url or "",
    }


def project_submission_fields(
    project: Project,
    submission: ProjectSubmission,
) -> list[dict]:
    fields = [
        project_repository_submission_field(submission),
        project_commit_submission_field(submission),
        project_learning_in_public_submission_field(
            project, submission
        ),
        project_time_submission_field(project, submission),
        project_problems_comments_submission_field(project, submission),
        project_faq_contribution_submission_field(project, submission),
    ]

    return [field for field in fields if field is not None]


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
    project_submission = project_submission_for_update(project, user)

    update_user_certificate_name_from_post(request, user)
    apply_project_submission_post_fields(
        request,
        project,
        project_submission,
    )

    return project_submission


def project_submission_for_update(
    project: Project,
    user: User,
) -> ProjectSubmission:
    project_submission = ProjectSubmission.objects.filter(
        project=project,
        student=user,
        volunteer_review_only=False,
    ).first()

    if project_submission:
        project_submission.submitted_at = timezone.now()
        return project_submission

    enrollment, _ = Enrollment.objects.get_or_create(
        student=user,
        course=project.course,
    )
    return ProjectSubmission(
        project=project,
        student=user,
        enrollment=enrollment,
    )


def update_user_certificate_name_from_post(
    request: HttpRequest,
    user: User,
) -> None:
    certificate_name = request.POST.get("certificate_name", "").strip()
    if not certificate_name:
        return

    user.certificate_name = certificate_name
    user.save(update_fields=["certificate_name"])


def apply_project_submission_post_fields(
    request: HttpRequest,
    project: Project,
    project_submission: ProjectSubmission,
) -> None:
    project_submission.github_link = request.POST.get("github_link")
    project_submission.commit_id = request.POST.get("commit_id")
    apply_project_submission_optional_post_fields(
        request,
        project,
        project_submission,
    )


def apply_project_submission_optional_post_fields(
    request: HttpRequest,
    project: Project,
    project_submission: ProjectSubmission,
) -> None:
    if project.learning_in_public_cap_project > 0:
        apply_project_learning_in_public_links(
            request,
            project,
            project_submission,
        )

    if project.time_spent_project_field:
        apply_project_time_spent(request, project_submission)

    if project.problems_comments_field:
        apply_project_problems_comments(request, project_submission)

    if project.faq_contribution_field:
        apply_project_faq_contribution_url(request, project_submission)


def apply_project_learning_in_public_links(
    request: HttpRequest,
    project: Project,
    project_submission: ProjectSubmission,
) -> None:
    links = request.POST.getlist("learning_in_public_links[]")
    cleaned_links = clean_learning_in_public_links(
        links, project.learning_in_public_cap_project
    )
    project_submission.learning_in_public_links = cleaned_links


def apply_project_time_spent(
    request: HttpRequest,
    project_submission: ProjectSubmission,
) -> None:
    time_spent = request.POST.get("time_spent")
    if time_spent is not None and time_spent != "":
        project_submission.time_spent = tryparsefloat(time_spent)


def apply_project_problems_comments(
    request: HttpRequest,
    project_submission: ProjectSubmission,
) -> None:
    problems_comments = request.POST.get("problems_comments", "")
    project_submission.problems_comments = problems_comments.strip()


def apply_project_faq_contribution_url(
    request: HttpRequest,
    project_submission: ProjectSubmission,
) -> None:
    faq_contribution_url = request.POST.get("faq_contribution_url", "")
    project_submission.faq_contribution_url = faq_contribution_url.strip()


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


def project_redirect(course: Course, project: Project):
    return redirect(
        "project",
        course_slug=course.slug,
        project_slug=project.slug,
    )


def project_login_required_response(
    request: HttpRequest, course: Course, project: Project
):
    messages.error(
        request,
        "You need to be logged in to submit a project",
        extra_tags="homework",
    )
    return project_redirect(course, project)


def closed_project_submission_response(
    request: HttpRequest, course: Course, project: Project
):
    messages.error(
        request,
        "Project submission form is closed.",
        extra_tags="homework",
    )
    context = project_build_context(request, course, project)
    return render(request, "projects/project.html", context)


def is_delete_project_submission_request(request: HttpRequest) -> bool:
    return "action" in request.POST and request.POST["action"] == "delete"


def project_validation_error_response(
    request: HttpRequest,
    course: Course,
    project: Project,
    error: ValidationError,
):
    for message in error.messages:
        messages.error(
            request,
            f"Failed to submit the project: {message}",
            extra_tags="alert-danger",
        )
    context = project_build_context(request, course, project)
    context["submission"] = project_submission_from_post(request, project)
    return render(request, "projects/project.html", context)


def handle_project_post(
    request: HttpRequest,
    course: Course,
    project: Project,
    accepting_submissions: bool,
):
    if not request.user.is_authenticated:
        return project_login_required_response(request, course, project)

    if not accepting_submissions:
        return closed_project_submission_response(
            request, course, project
        )

    if is_delete_project_submission_request(request):
        project_delete_submission(request, project)
    else:
        try:
            project_submit_post(request, project)
        except ValidationError as error:
            return project_validation_error_response(
                request, course, project, error
            )

    return project_redirect(course, project)


def project_view(request, course_slug, project_slug):
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, course=course, slug=project_slug
    )

    accepting_submissions = (
        project.state == ProjectState.COLLECTING_SUBMISSIONS.value
    )

    if request.method == "POST":
        return handle_project_post(
            request,
            course,
            project,
            accepting_submissions,
        )

    context = project_build_context(request, course, project)

    return render(request, "projects/project.html", context)


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

    return assigned_reviews, selected_reviews, completed_count


def student_project_eval_context(course, project, user, eval_closed):
    student_submissions = student_project_submissions(project, user)
    project_submissions = student_submissions.filter(
        volunteer_review_only=False,
    )
    reviews = project_eval_reviews(project, student_submissions)
    assigned_reviews, selected_reviews, completed_count = (
        split_project_eval_reviews(reviews)
    )

    return {
        "course": course,
        "project": project,
        "reviews": reviews,
        "assigned_reviews": assigned_reviews,
        "selected_reviews": selected_reviews,
        "is_authenticated": True,
        "number_of_completed_evaluation": completed_count,
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
    context = _project_results_context(course, project, request.user)

    return render(request, "projects/results.html", context)


def _project_results_context(course, project, user):
    if not user.is_authenticated:
        return _anonymous_project_results_context(course, project)

    submission = _project_results_submission(project, user)
    return {
        "course": course,
        "project": project,
        "submission": submission,
        "scores": _project_results_scores(submission),
        "feedback": _project_results_feedback(submission),
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
    scores = list(
        ProjectEvaluationScore.objects.filter(submission=submission)
        .order_by("review_criteria__id")
        .prefetch_related("review_criteria")
    )
    annotate_scores_with_option_votes(submission, scores)
    return scores


def _project_results_feedback(submission):
    return list(
        PeerReview.objects.filter(
            submission_under_evaluation=submission,
            state=PeerReviewState.SUBMITTED.value,
            note_to_peer__isnull=False,
            note_to_peer__gt="",
        )
    )


def criteria_response_answer_indexes(response):
    if response is None:
        return set()

    answers = (response.answer or "").strip().split(",")
    return {int(answer) for answer in answers if answer}


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
        criteria_response_pairs.append((criteria, response))
    return criteria_response_pairs


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

    disable_learning_in_public = (
        enrollment.disable_learning_in_public if enrollment else False
    )
    responses_by_criteria_id = {
        response.criteria.id: response
        for response in review.get_criteria_responses()
    }

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
        "disable_learning_in_public": disable_learning_in_public,
    }

    return context


def project_eval_answers_from_post(post_data):
    answers = {}
    for answer_id, answer in post_data.lists():
        if not answer_id.startswith("answer_"):
            continue
        answers[answer_id] = ",".join(
            value.strip() for value in answer
        )
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


def _project_eval_submit_context(request, course, project, review, criteria):
    enrollment, _ = Enrollment.objects.get_or_create(
        student=request.user,
        course=course,
    )
    context = project_eval_build_context(
        project,
        review,
        criteria,
        enrollment,
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
    course,
    project,
    review,
    review_criteria,
):
    messages.error(
        request,
        "Peer review form is closed.",
        extra_tags="homework",
    )
    context = _project_eval_submit_context(
        request,
        course,
        project,
        review,
        review_criteria,
    )
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
    course,
    project,
    review,
    review_criteria,
):
    if request.POST.get("form_action") == "vote":
        return _project_eval_vote_response(
            request,
            course.slug,
            project.slug,
            review,
        )

    if project.state != ProjectState.PEER_REVIEWING.value:
        return _closed_project_eval_response(
            request,
            course,
            project,
            review,
            review_criteria,
        )

    project_eval_post_submission(
        request, project, review, review_criteria
    )
    return _redirect_to_projects_eval(course.slug, project.slug)


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

    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(
        Project, slug=project_slug, course=course
    )

    review_criteria = ReviewCriteria.objects.filter(
        course=course
    ).order_by("id")

    if request.method == "POST":
        return _projects_eval_submit_post_response(
            request,
            course,
            project,
            review,
            review_criteria,
        )

    context = _project_eval_submit_context(
        request,
        course,
        project,
        review,
        review_criteria,
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
        _decorate_submission_review_state(submission, review_ids)
        _decorate_submission_viewer_state(
            submission,
            project=project,
            own_submissions=own_submissions,
            voted_submission_ids=voted_submission_ids,
            project_vote_counts=project_vote_counts,
        )
        _decorate_submission_review_group(
            submission,
            in_peer_review=in_peer_review,
            has_assigned_reviews=has_assigned_reviews,
        )


def _decorate_submission_review_state(submission, review_ids):
    if submission.id in review_ids:
        submission.to_evaluate = True
        submission.review = review_ids[submission.id]
        return

    submission.to_evaluate = False


def _decorate_submission_viewer_state(
    submission,
    *,
    project,
    own_submissions,
    voted_submission_ids,
    project_vote_counts,
):
    submission.own = submission.id in own_submissions
    submission.vote_limit_reached = (
        submission.id not in voted_submission_ids
        and project_vote_counts.get(project.id, 0)
        >= PROJECT_VOTES_PER_PROJECT
    )


def _decorate_submission_review_group(
    submission,
    *,
    in_peer_review,
    has_assigned_reviews,
):
    submission.group_order = 1
    submission.group_label = None

    if not in_peer_review:
        return

    if submission.to_evaluate and not submission.review.optional:
        submission.group_order = 0
        submission.group_label = "Assigned reviews"
        return

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
