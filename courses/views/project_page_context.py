from dataclasses import dataclass

from courses.models.course import Course, Enrollment, User
from courses.models.project import (
    Project,
    ProjectSubmission,
    ProjectState,
)


@dataclass(frozen=True)
class ProjectContextUserDetails:
    submission: ProjectSubmission | None
    enrollment: Enrollment | None
    certificate_name: str | None


def project_build_context(request, course: Course, project: Project) -> dict:
    user = request.user
    is_authenticated = user.is_authenticated
    accepting_submissions = project_accepting_submissions(project)
    if is_authenticated:
        user_details = project_context_user_details(user, course, project)
    else:
        user_details = ProjectContextUserDetails(None, None, None)
    disable_learning_in_public = project_learning_in_public_disabled(
        user_details.enrollment
    )

    return {
        "course": course,
        "project": project,
        "submission": user_details.submission,
        "is_authenticated": is_authenticated,
        "disabled": not accepting_submissions,
        "accepting_submissions": accepting_submissions,
        "certificate_name": user_details.certificate_name,
        "disable_learning_in_public": disable_learning_in_public,
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
    certificate_name = project_context_certificate_name(user, enrollment)
    return ProjectContextUserDetails(
        submission=project_submission,
        enrollment=enrollment,
        certificate_name=certificate_name,
    )


def project_context_submission(
    user: User,
    project: Project,
) -> ProjectSubmission | None:
    return ProjectSubmission.objects.filter(
        project=project,
        student=user,
        volunteer_review_only=False,
    ).first()


def project_context_certificate_name(
    user: User,
    enrollment: Enrollment,
) -> str | None:
    if user.certificate_name:
        return user.certificate_name
    return enrollment.display_name


def project_learning_in_public_disabled(
    enrollment: Enrollment | None,
) -> bool:
    if enrollment is None:
        return False
    return enrollment.disable_learning_in_public
