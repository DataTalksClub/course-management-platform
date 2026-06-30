import logging

from typing import Optional
from dataclasses import dataclass

from django.http import HttpRequest

from django.contrib import messages
from django.utils import timezone
from django.shortcuts import render, get_object_or_404, redirect
from django.core.exceptions import ValidationError
from django.db import transaction

from course_management.datamailer import sync_project_submission_to_datamailer
from courses.models import (
    Course,
    Enrollment,
    Project,
    ProjectSubmission,
    ProjectState,
    User,
)

from .homework_learning_links import clean_learning_in_public_links
from .submission_formatting import (
    tryparsefloat,
)
from .project_confirmation import (
    ProjectConfirmationEmailData,
    build_project_update_url,
    send_project_confirmation_email,
)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProjectContextUserDetails:
    submission: Optional[ProjectSubmission]
    enrollment: Optional[Enrollment]
    certificate_name: Optional[str]


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
    confirmation_data = ProjectConfirmationEmailData(
        user=request.user,
        course=project.course,
        project=project,
        submission=project_submission,
        update_url=update_url,
    )
    transaction.on_commit(
        lambda: sync_project_submission_to_datamailer(
            project_submission
        )
    )
    transaction.on_commit(
        lambda: send_project_confirmation_email(confirmation_data)
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
    accepting_submissions = project_accepting_submissions(project)
    if is_authenticated:
        user_details = project_context_user_details(user, course, project)
    else:
        user_details = ProjectContextUserDetails(None, None, None)

    return {
        "course": course,
        "project": project,
        "submission": user_details.submission,
        "is_authenticated": is_authenticated,
        "disabled": not accepting_submissions,
        "accepting_submissions": accepting_submissions,
        "certificate_name": user_details.certificate_name,
        "disable_learning_in_public": project_learning_in_public_disabled(
            user_details.enrollment
        ),
    }


def project_accepting_submissions(project: Project) -> bool:
    return project.state == ProjectState.COLLECTING_SUBMISSIONS.value


def project_context_user_details(
    user: User,
    course: Course,
    project: Project,
) -> ProjectContextUserDetails:
    project_submission = project_context_submission(user, project)
    enrollment, _ = Enrollment.objects.get_or_create(
        student=user,
        course=course,
    )
    return ProjectContextUserDetails(
        submission=project_submission,
        enrollment=enrollment,
        certificate_name=project_context_certificate_name(user, enrollment),
    )


def project_context_submission(
    user: User,
    project: Project,
) -> Optional[ProjectSubmission]:
    return ProjectSubmission.objects.filter(
        project=project,
        student=user,
        volunteer_review_only=False,
    ).first()


def project_context_certificate_name(
    user: User,
    enrollment: Enrollment,
) -> Optional[str]:
    return user.certificate_name or enrollment.display_name


def project_learning_in_public_disabled(
    enrollment: Optional[Enrollment],
) -> bool:
    return enrollment.disable_learning_in_public if enrollment else False


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
    error_messages = error.messages
    for message in error_messages:
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
