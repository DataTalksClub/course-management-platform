from enum import Enum

from django.utils import timezone

from .models import Homework, Submission
from .models import QuestionTypes, AnswerTypes


class HomeworkScoringStatus(Enum):
    OK = "OK"
    FAIL = "Warning"


def is_float_equal(value1, value2, tolerance=0.01):
    try:
        return abs(float(value1) - float(value2)) <= tolerance
    except ValueError:
        return False


def is_integer_equal(value1, value2):
    try:
        return int(value1) == int(value2)
    except ValueError:
        return False


def is_answer_correct(question, user_answer):
    if question.answer_type == AnswerTypes.ANY.value:
        return True

    correct_answer = question.correct_answer

    if question.question_type == QuestionTypes.MULTIPLE_CHOICE.value:
        return user_answer == correct_answer

    elif question.question_type == QuestionTypes.CHECKBOXES.value:
        selected_options = set(user_answer.split(','))
        correct_options = set(correct_answer.split(','))
        return selected_options == correct_options

    elif question.question_type == QuestionTypes.FREE_FORM.value:
        user_answer = user_answer.strip().lower()
        correct_answer = correct_answer.strip().lower()

        if question.answer_type == AnswerTypes.EXACT_STRING.value:
            return user_answer == correct_answer
        elif question.answer_type == AnswerTypes.CONTAINS_STRING.value:
            return correct_answer in user_answer
        elif question.answer_type == AnswerTypes.FLOAT.value:
            return is_float_equal(user_answer, correct_answer)
        elif question.answer_type == AnswerTypes.INTEGER.value:
            return is_integer_equal(user_answer, correct_answer)

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


def score_homework_submissions(homework_id: str) -> tuple[HomeworkScoringStatus, str]:
    homework = Homework.objects.get(pk=homework_id)

    if homework.due_date > timezone.now():
        return HomeworkScoringStatus.FAIL, f"The due date for {homework} is in the future. Update the due date to score."

    if homework.is_scored:
        return HomeworkScoringStatus.FAIL, f"Homework {homework} is already scored."

    submissions = Submission.objects.filter(homework__id=homework_id)

    for submission in submissions:
        update_score(submission)

    homework.is_scored = True
    homework.save()

    return HomeworkScoringStatus.OK, f"Homework {homework} is scored"