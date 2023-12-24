import logging

from enum import Enum

from django.utils import timezone
from django.db.models import Subquery, OuterRef, Sum

from .models import (
    Homework,
    Submission,
    Question,
    Course,
    QuestionTypes,
    AnswerTypes,
    Enrollment
)




logger = logging.getLogger(__name__)


class HomeworkScoringStatus(Enum):
    OK = "OK"
    FAIL = "Warning"


def is_float_equal(value1: str, value2: str, tolerance: float=0.01) -> bool:
    try:
        return abs(float(value1) - float(value2)) <= tolerance
    except ValueError:
        return False


def is_integer_equal(value1: str, value2: str) -> bool:
    try:
        return int(value1) == int(value2)
    except ValueError:
        return False


def is_free_form_answer_correct(
    user_answer: str, correct_answer: str, answer_type: str
):
    if answer_type == AnswerTypes.ANY.value:
        return True

    user_answer = (user_answer or "").strip().lower()
    correct_answer = (correct_answer or "").strip().lower()

    if answer_type == AnswerTypes.EXACT_STRING.value:
        return user_answer == correct_answer
    elif answer_type == AnswerTypes.CONTAINS_STRING.value:
        return correct_answer in user_answer
    elif answer_type == AnswerTypes.FLOAT.value:
        return is_float_equal(user_answer, correct_answer, tolerance=0.01)
    elif answer_type == AnswerTypes.INTEGER.value:
        return is_integer_equal(user_answer, correct_answer)

    return False


def is_answer_correct(question: Question, user_answer: str) -> bool:
    if question.answer_type == AnswerTypes.ANY.value:
        return True

    correct_answer = question.correct_answer

    if question.question_type == QuestionTypes.MULTIPLE_CHOICE.value:
        return user_answer == correct_answer

    elif question.question_type == QuestionTypes.CHECKBOXES.value:
        selected_options = set(user_answer.split(","))
        correct_options = set(correct_answer.split(","))
        return selected_options == correct_options

    elif question.question_type == QuestionTypes.FREE_FORM.value:
        return is_free_form_answer_correct(
            user_answer, correct_answer, question.answer_type
        )

    return False


def update_score(submission: Submission):
    total_score = 0

    for answer, question in submission.answers_with_questions:
        is_correct = is_answer_correct(question, answer.answer_text)

        answer.is_correct = is_correct
        answer.save()

        if is_correct:
            total_score += question.scores_for_correct_answer

    submission.total_score = total_score
    submission.save()


def update_leaderboard(course: Course):
    scored_homeworks = Homework.objects \
        .filter(course=course, is_scored=True)

    aggregated_scores = Submission.objects \
        .filter(homework__in=scored_homeworks) \
        .values('enrollment') \
        .annotate(total_score=Sum('total_score'))

    # Update each enrollment with the aggregated score
    for aggregated_score in aggregated_scores:
        Enrollment.objects \
            .filter(id=aggregated_score['enrollment']) \
            .update(total_score=aggregated_score['total_score'])



def score_homework_submissions(homework_id: str) -> tuple[HomeworkScoringStatus, str]:
    homework = Homework.objects.get(pk=homework_id)

    if homework.due_date > timezone.now():
        return (
            HomeworkScoringStatus.FAIL,
            f"The due date for {homework} is in the future. Update the due date to score.",
        )

    if homework.is_scored:
        return HomeworkScoringStatus.FAIL, f"Homework {homework} is already scored."

    submissions = Submission.objects.filter(homework__id=homework_id)

    for submission in submissions:
        update_score(submission)

    homework.is_scored = True
    homework.save()

    update_leaderboard(homework.course)

    logger.info(f"Scored {len(submissions)} submissions for {homework}")

    return HomeworkScoringStatus.OK, f"Homework {homework} is scored"
