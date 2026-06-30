import logging

from typing import Optional
from dataclasses import dataclass

from django.http import HttpRequest

from django.contrib import messages
from django.utils import timezone
from django.shortcuts import render, get_object_or_404, redirect
from django.core.exceptions import ValidationError
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
    User,
)

from courses.views.url_utils import absolute_url_with_fallback

from .homework import (
    build_account_settings_url,
    clean_learning_in_public_links,
    format_hours,
    format_submission_lines,
    request_base_url,
    tryparsefloat,
)
from .project_eval import (
    projects_eval_add as projects_eval_add,
    projects_eval_delete as projects_eval_delete,
    projects_eval_submit as projects_eval_submit,
    projects_eval_view as projects_eval_view,
)
from .project_results import project_results as project_results
from .project_statistics import project_statistics as project_statistics
from .project_submissions import (
    project_submissions as project_submissions,
    projects_list_view as projects_list_view,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProjectConfirmationEmailData:
    user: User
    course: Course
    project: Project
    submission: ProjectSubmission
    update_url: str


@dataclass(frozen=True)
class ProjectConfirmationData:
    course: Course
    project: Project
    submission: ProjectSubmission
    update_url: str
    profile_url: str


@dataclass(frozen=True)
class ProjectContextUserDetails:
    submission: Optional[ProjectSubmission]
    enrollment: Optional[Enrollment]
    certificate_name: Optional[str]


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


def project_required_submission_fields(
    submission: ProjectSubmission,
) -> list[dict]:
    fields = []
    repository_field = project_repository_submission_field(submission)
    fields.append(repository_field)
    commit_field = project_commit_submission_field(submission)
    fields.append(commit_field)
    return fields


def project_optional_submission_fields(
    project: Project,
    submission: ProjectSubmission,
) -> list[dict | None]:
    fields = []
    learning_in_public_field = project_learning_in_public_submission_field(
        project,
        submission,
    )
    fields.append(learning_in_public_field)
    time_field = project_time_submission_field(project, submission)
    fields.append(time_field)
    problems_comments_field = project_problems_comments_submission_field(
        project,
        submission,
    )
    fields.append(problems_comments_field)
    faq_contribution_field = project_faq_contribution_submission_field(
        project,
        submission,
    )
    fields.append(faq_contribution_field)
    return fields


def visible_project_submission_fields(fields: list[dict | None]) -> list[dict]:
    visible_fields = []
    for field in fields:
        if field is not None:
            visible_fields.append(field)
    return visible_fields


def project_submission_fields(
    project: Project,
    submission: ProjectSubmission,
) -> list[dict]:
    fields = []
    required_fields = project_required_submission_fields(submission)
    fields.extend(required_fields)
    optional_fields = project_optional_submission_fields(
        project,
        submission,
    )
    fields.extend(optional_fields)
    return visible_project_submission_fields(fields)


def project_confirmation_metadata(
    data: ProjectConfirmationData,
) -> dict:
    return {
        "course_slug": data.course.slug,
        "course_title": data.course.title,
        "project_slug": data.project.slug,
        "project_title": data.project.title,
        "project_due_at": data.project.submission_due_date.isoformat(),
        "submission_id": data.submission.id,
        "submitted_at": data.submission.submitted_at.isoformat(),
        "update_url": data.update_url,
        "profile_url": data.profile_url,
        "update_link_text": "Update your submission",
    }


def project_confirmation_notification_context(profile_url: str) -> dict:
    return {
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
    }


def project_confirmation_message_context(
    data: ProjectConfirmationData,
) -> dict:
    return {
        "email_subject": f"Project submission saved: {data.project.title}",
        "email_preview": (
            "Your project submission was saved. Review what you "
            "submitted and update it while the project is open."
        ),
        "intro_text": (
            f"Your project submission for {data.project.title} in "
            f"{data.course.title} was saved."
        ),
        "update_text": (
            "You can update your submission while the project "
            f"is open: {data.update_url}"
        ),
    }


def project_confirmation_context(
    data: ProjectConfirmationData,
) -> dict:
    submission_fields = project_submission_fields(
        data.project,
        data.submission,
    )
    submitted_fields_text = format_submission_lines(submission_fields)

    return {
        **project_confirmation_metadata(data),
        **project_confirmation_notification_context(data.profile_url),
        **project_confirmation_message_context(data),
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


def send_project_confirmation_email(data: ProjectConfirmationEmailData) -> None:
    if not data.user.email:
        return

    payload = project_confirmation_payload(data)
    send_transactional_email(payload)


def project_confirmation_payload(data: ProjectConfirmationEmailData) -> dict:
    return {
        "email": data.user.email,
        "template_key": email_templates.PROJECT_SUBMISSION_CONFIRMATION,
        "category_tag": "submission-results",
        "idempotency_key": project_confirmation_idempotency_key(
            data.submission
        ),
        "context": project_confirmation_payload_context(data),
        "metadata": project_confirmation_email_metadata(data),
    }


def project_confirmation_payload_context(
    data: ProjectConfirmationEmailData,
) -> dict:
    profile_url = build_account_settings_url(request_base_url(data.update_url))
    context_data = ProjectConfirmationData(
        course=data.course,
        project=data.project,
        submission=data.submission,
        update_url=data.update_url,
        profile_url=profile_url,
    )
    return project_confirmation_context(context_data)


def project_confirmation_idempotency_key(
    submission: ProjectSubmission,
) -> str:
    return (
        f"project-submission:{submission.id}:"
        f"{submission.submitted_at.isoformat()}"
    )


def project_confirmation_email_metadata(
    data: ProjectConfirmationEmailData,
) -> dict:
    return {
        "source": "course-management-platform",
        "event": "project_submission",
        "course_slug": data.course.slug,
        "project_slug": data.project.slug,
        "submission_id": data.submission.id,
    }


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
