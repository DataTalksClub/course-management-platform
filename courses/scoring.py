from enum import Enum

from django.utils import timezone

from .models import Homework, Submission
from .models import QuestionTypes, AnswerTypes


class HomeworkScoringStatus(Enum):
    OK = "OK"
    FAIL = "Warning"


def update_score(submission: Submission) -> int:
    total_score = 0

    for answer, question in submission.answers_with_questions:
        # Normalize strings for comparison: remove whitespace and convert to lowercase
        user_answer = answer.answer_text.strip().lower()
        correct_answer = question.correct_answer.strip().lower()

        is_correct = False

        if question.question_type == QuestionTypes.MULTIPLE_CHOICE:
            is_correct = user_answer == correct_answer

        elif question.question_type == QuestionTypes.FREE_FORM:
            if question.answer_type == AnswerTypes.ANY:
                is_correct = True  # Any answer is correct
            elif question.answer_type == AnswerTypes.EXACT_STRING:
                is_correct = user_answer == correct_answer
            elif question.answer_type == AnswerTypes.CONTAINS_STRING:
                is_correct = correct_answer in user_answer

        elif question.question_type == QuestionTypes.CHECKBOXES:
            # Normalize and compare checkbox answers
            selected_options = set(user_answer.split(','))
            correct_options = set(correct_answer.split(','))
            is_correct = selected_options == correct_options

        # Update the answer and total score
        answer.is_correct = is_correct
        answer.save()

        if is_correct:
            total_score += question.scores_for_correct_answer

    submission.total_score = total_score
    submission.save()

    return total_score


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