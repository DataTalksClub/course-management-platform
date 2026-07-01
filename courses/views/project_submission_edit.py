from functools import partial

from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from course_management.datamailer.sync.memberships import (
    sync_project_submission_to_datamailer,
)
from courses.models import Enrollment, Project, ProjectSubmission, User
from courses.views.homework_learning_links import (
    clean_learning_in_public_links,
)
from courses.views.project_confirmation import (
    ProjectConfirmationEmailData,
    build_project_update_url,
    send_project_confirmation_email,
)
from courses.views.submission_formatting import tryparsefloat


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
    sync_callback = partial(
        sync_project_submission_to_datamailer,
        project_submission,
    )
    email_callback = partial(
        send_project_confirmation_email,
        confirmation_data,
    )
    transaction.on_commit(sync_callback)
    transaction.on_commit(email_callback)


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
    raw_certificate_name = request.POST.get("certificate_name", "")
    certificate_name = raw_certificate_name.strip()
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
