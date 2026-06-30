from typing import List, Optional

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator

from courses.models import Course, ProjectSubmission, Submission, User


def _invalid_learning_in_public_link_error():
    return ValidationError(
        "Learning in public links must be valid HTTP or HTTPS URLs."
    )


def _validate_learning_in_public_link(url_validator, link):
    try:
        url_validator(link)
    except ValidationError:
        raise _invalid_learning_in_public_link_error()


def _is_blank_or_duplicate_link(link, cleaned_links):
    return len(link) == 0 or link in cleaned_links


def clean_learning_in_public_links(
    links: List[str], cap: int
) -> List[str]:
    url_validator = URLValidator(schemes=["http", "https"])
    cleaned_links = []

    for link in links:
        link = link.strip()
        if _is_blank_or_duplicate_link(link, cleaned_links):
            continue
        if len(cleaned_links) >= cap:
            break

        _validate_learning_in_public_link(url_validator, link)
        cleaned_links.append(link)

    return cleaned_links


def find_duplicate_learning_in_public_links(
    user: User,
    course: Course,
    links: List[str],
    current_submission: Optional[Submission],
) -> List[str]:
    if not links:
        return []

    candidate_links = set(links)
    duplicate_links = _duplicate_homework_learning_links(
        user=user,
        course=course,
        candidate_links=candidate_links,
        current_submission=current_submission,
    )
    project_duplicate_links = _duplicate_project_learning_links(
        user=user,
        course=course,
        candidate_links=candidate_links,
    )
    duplicate_links.update(project_duplicate_links)

    return sorted(duplicate_links)


def _duplicate_homework_learning_links(
    *, user, course, candidate_links, current_submission
):
    submissions = _homework_submissions_with_learning_links(user, course)
    submissions = _exclude_current_submission(submissions, current_submission)
    return _duplicate_learning_links_from_submissions(
        submissions,
        candidate_links,
    )


def _homework_submissions_with_learning_links(user, course):
    return Submission.objects.filter(
        student=user,
        homework__course=course,
        learning_in_public_links__isnull=False,
    )


def _exclude_current_submission(submissions, current_submission):
    if current_submission and current_submission.pk:
        return submissions.exclude(pk=current_submission.pk)
    return submissions


def _duplicate_project_learning_links(*, user, course, candidate_links):
    submissions = ProjectSubmission.objects.filter(
        student=user,
        project__course=course,
        volunteer_review_only=False,
        learning_in_public_links__isnull=False,
    )
    return _duplicate_learning_links_from_submissions(
        submissions,
        candidate_links,
    )


def _duplicate_learning_links_from_submissions(submissions, candidate_links):
    duplicate_links = set()
    for submission in submissions:
        matching_links = _matching_learning_links(
            submission,
            candidate_links,
        )
        duplicate_links.update(matching_links)
    return duplicate_links


def _matching_learning_links(submission, candidate_links):
    matching_links = set()
    learning_links = submission.learning_in_public_links or []
    for link in learning_links:
        if link in candidate_links:
            matching_links.add(link)
    return matching_links
