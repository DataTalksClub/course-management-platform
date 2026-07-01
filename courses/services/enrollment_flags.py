from django.db import transaction

from courses.models.homework import Submission
from courses.models.project import ProjectSubmission
from courses.leaderboard import update_leaderboard


@transaction.atomic
def set_learning_in_public_disabled(enrollment, disabled: bool):
    enrollment.disable_learning_in_public = disabled
    enrollment.save(update_fields=["disable_learning_in_public"])

    if disabled:
        _zero_homework_learning_in_public_scores(enrollment)
        _zero_project_learning_in_public_scores(enrollment)

    update_leaderboard(enrollment.course)


def _zero_homework_learning_in_public_scores(enrollment):
    submissions_to_update = []
    submissions = Submission.objects.filter(enrollment=enrollment)
    for submission in submissions:
        if submission.learning_in_public_score <= 0:
            continue
        submission.learning_in_public_score = 0
        submission.total_score = _homework_total_without_learning_in_public(
            submission
        )
        submissions_to_update.append(submission)

    if submissions_to_update:
        Submission.objects.bulk_update(
            submissions_to_update,
            ["learning_in_public_score", "total_score"],
        )


def _zero_project_learning_in_public_scores(enrollment):
    submissions_to_update = []
    submissions = ProjectSubmission.objects.filter(enrollment=enrollment)
    for submission in submissions:
        if not _project_has_learning_in_public_score(submission):
            continue
        submission.project_learning_in_public_score = 0
        submission.peer_review_learning_in_public_score = 0
        submission.total_score = _project_total_without_learning_in_public(
            submission
        )
        submissions_to_update.append(submission)

    if submissions_to_update:
        ProjectSubmission.objects.bulk_update(
            submissions_to_update,
            [
                "project_learning_in_public_score",
                "peer_review_learning_in_public_score",
                "total_score",
            ],
        )


def _homework_total_without_learning_in_public(submission):
    return submission.questions_score + submission.faq_score


def _project_has_learning_in_public_score(submission):
    return (
        submission.project_learning_in_public_score > 0
        or submission.peer_review_learning_in_public_score > 0
    )


def _project_total_without_learning_in_public(submission):
    return (
        submission.project_score
        + submission.project_faq_score
        + submission.peer_review_score
    )
