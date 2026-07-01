from courses.models import Project, ProjectSubmission
from courses.views.homework_answers import format_hours


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
    value = "\n".join(links)
    return {
        "key": "learning_in_public_links",
        "label": "Learning in public links",
        "value": value,
        "values": links,
    }


def project_time_submission_field(
    project: Project,
    submission: ProjectSubmission,
) -> dict | None:
    if not project.time_spent_project_field:
        return None

    value = format_hours(submission.time_spent)
    return {
        "key": "time_spent",
        "label": "Time spent on project",
        "value": value,
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
