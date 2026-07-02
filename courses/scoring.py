import logging

from time import time
from enum import Enum
from dataclasses import dataclass
from collections import defaultdict

from django.utils import timezone

from django.db import transaction

from . import assignment_statistics, leaderboard
from .homework_score_calculation import update_score

from .models.homework import (
    Answer,
    Homework,
    HomeworkState,
    Submission,
)


logger = logging.getLogger(__name__)


class HomeworkScoringStatus(Enum):
    OK = "OK"
    FAIL = "Warning"


@dataclass(frozen=True)
class HomeworkScoringBatch:
    submissions: object
    answers: object
    answers_by_submission_id: dict


def _homework_scoring_error(homework, homework_id):
    if homework.due_date > timezone.now():
        return (
            "The due date for "
            f"{homework_id} is in the future. Update the due date to score."
        )
    if homework.state == HomeworkState.CLOSED.value:
        return (
            f"Homework {homework_id} is closed. "
            "Update the state to OPEN to score."
        )
    if homework.state == HomeworkState.SCORED.value:
        return f"Homework {homework_id} is already scored."
    return None


def _answers_by_submission(answers):
    answers_by_submission_id = defaultdict(list)
    for answer in answers:
        answers_by_submission_id[answer.submission_id].append(answer)
    return answers_by_submission_id


def _score_homework_submission_batch(
    submissions,
    answers_by_submission_id,
):
    for submission in submissions:
        submission_answers = answers_by_submission_id[submission.id]
        update_score(submission, submission_answers, save=False)


def _persist_scored_homework_submissions(homework_id, submissions, answers):
    logger.info(f"Updating the submissions for homework {homework_id}")
    Submission.objects.bulk_update(
        submissions,
        [
            "questions_score",
            "learning_in_public_score",
            "faq_score",
            "total_score",
        ],
    )

    logger.info(f"Updating answers for homework {homework_id}")
    Answer.objects.bulk_update(answers, ["is_correct"])


def _homework_scoring_batch(homework_id):
    submissions = Submission.objects.filter(homework__id=homework_id)
    answers = Answer.objects.filter(
        submission__in=submissions
    ).select_related("question", "submission")
    answers_by_submission_id = _answers_by_submission(answers)
    return HomeworkScoringBatch(
        submissions=submissions,
        answers=answers,
        answers_by_submission_id=answers_by_submission_id,
    )


def _mark_homework_scored(homework):
    homework.state = HomeworkState.SCORED.value
    homework.save()

    course = homework.course
    leaderboard.update_leaderboard(course)

    course.first_homework_scored = True
    course.save()

    assignment_statistics.calculate_homework_statistics(homework, force=True)


def _homework_scoring_success(homework_id, started_at):
    duration = time() - started_at
    logger.info(f"Scored homework in {duration:.2f} seconds")
    message = f"Homework {homework_id} is scored"
    return (
        HomeworkScoringStatus.OK,
        message,
    )


def _score_and_persist_homework_submissions(homework_id):
    batch = _homework_scoring_batch(homework_id)
    logger.info(
        f"Scoring {len(batch.answers_by_submission_id)} submissions for homework {homework_id}"
    )

    _score_homework_submission_batch(
        batch.submissions,
        batch.answers_by_submission_id,
    )
    _persist_scored_homework_submissions(
        homework_id,
        batch.submissions,
        batch.answers,
    )

    logger.info(
        f"Scored {len(batch.submissions)} submissions for homework {homework_id}"
    )


def score_homework_submissions(
    homework_id: str,
) -> tuple[HomeworkScoringStatus, str]:
    with transaction.atomic():
        t0 = time()
        logger.info(f"Scoring submissions for homework {homework_id}")

        homework = Homework.objects.get(pk=homework_id)

        if error := _homework_scoring_error(homework, homework_id):
            return (HomeworkScoringStatus.FAIL, error)

        _score_and_persist_homework_submissions(homework_id)
        _mark_homework_scored(homework)

        return _homework_scoring_success(homework_id, t0)
