from dataclasses import dataclass

from courses.models.course import Course, Enrollment, User
from courses.models.project import (
    Project,
    ProjectSubmission,
    ProjectState,
)
from courses.registration_wall import (
    course_has_registration_wall,
    get_or_create_enrollment_for_content,
)
from courses.views.course_page_context import (
    active_registration_campaign_for_course,
)


@dataclass(frozen=True)
class ProjectContextUserDetails:
    submission: ProjectSubmission | None
    enrollment: Enrollment | None
    certificate_name: str | None
    wall_blocked: bool = False


def project_build_context(request, course: Course, project: Project) -> dict:
    user = request.user
    is_authenticated = user.is_authenticated
    accepting_submissions = project_accepting_submissions(project)
    if is_authenticated:
        user_details = project_context_user_details(user, course, project)
        wall_blocked = user_details.wall_blocked
    else:
        user_details = ProjectContextUserDetails(None, None, None)
        wall_blocked = course_has_registration_wall(course)
    disable_learning_in_public = project_learning_in_public_disabled(
        user_details.enrollment
    )

    return {
        "course": course,
        "project": project,
        "submission": user_details.submission,
        "has_submission": user_details.submission is not None,
        "is_authenticated": is_authenticated,
        "disabled": not accepting_submissions,
        "accepting_submissions": accepting_submissions,
        "certificate_name": user_details.certificate_name,
        "disable_learning_in_public": disable_learning_in_public,
        "registration_wall_blocked": wall_blocked,
        "registration_campaign": active_registration_campaign_for_course(
            course
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
    enrollment, wall_blocked = get_or_create_enrollment_for_content(
        user,
        course,
    )
    certificate_name = project_context_certificate_name(user, enrollment)
    return ProjectContextUserDetails(
        submission=project_submission,
        enrollment=enrollment,
        certificate_name=certificate_name,
        wall_blocked=wall_blocked,
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
    enrollment: Enrollment | None,
) -> str | None:
    if user.certificate_name:
        return user.certificate_name
    if enrollment is None:
        return None
    return enrollment.display_name


def project_learning_in_public_disabled(
    enrollment: Enrollment | None,
) -> bool:
    if enrollment is None:
        return False
    return enrollment.disable_learning_in_public
