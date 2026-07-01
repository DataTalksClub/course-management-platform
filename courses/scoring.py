import logging

from time import time
from enum import Enum
from dataclasses import dataclass
from collections import defaultdict

from django.utils import timezone
from django.db.models import Count

from django.db import transaction

from . import assignment_statistics, leaderboard
from .homework_score_calculation import update_score

from .models.homework import (
    Answer,
    Homework,
    HomeworkState,
    Question,
    QuestionTypes,
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
    logger.info(f"Scored homework in {(time() - started_at):.2f} seconds")
    return (
        HomeworkScoringStatus.OK,
        f"Homework {homework_id} is scored",
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


def fill_most_common_answer_as_correct(question: Question) -> None:
    if question.correct_answer and not has_invalid_correct_answer_indices(question):
        logger.info(f"Correct answer for {question} is already set")
        return

    answer_count = Count("answer_text")
    most_common_answer = (
        Answer.objects.filter(
            question=question,
            answer_text__isnull=False,
            answer_text__gt="",
        )
        .values("answer_text")
        .annotate(count=answer_count)
        .order_by("-count")
        .first()
    )

    if not most_common_answer:
        logger.warning(f"No answers for {question}")
        return

    answer = most_common_answer["answer_text"]
    question.correct_answer = answer
    question.save()
    logger.info(f"Updated answer for {question} to {answer}")


def _is_choice_question(question: Question) -> bool:
    return question.question_type in [
        QuestionTypes.MULTIPLE_CHOICE.value,
        QuestionTypes.CHECKBOXES.value,
    ]


def _correct_answer_indices(question: Question) -> list[int] | None:
    try:
        return question.get_correct_answer_indices()
    except ValueError:
        return None


def _has_out_of_range_answer_index(indices, possible_answers) -> bool:
    max_index = len(possible_answers)
    for index in indices:
        if index < 1 or index > max_index:
            return True
    return False


def has_invalid_correct_answer_indices(question: Question) -> bool:
    if not _is_choice_question(question):
        return False

    possible_answers = question.get_possible_answers()
    if not possible_answers:
        return False

    indices = _correct_answer_indices(question)
    if indices is None:
        return True

    return _has_out_of_range_answer_index(indices, possible_answers)


def fill_correct_answers(homework: Homework) -> None:
    questions = Question.objects.filter(homework=homework)

    for question in questions:
        fill_most_common_answer_as_correct(question)


def clear_correct_answers(homework: Homework) -> int:
    questions = Question.objects.filter(homework=homework)
    updated_count = questions.update(correct_answer="")
    return updated_count
