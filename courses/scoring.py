import logging

from enum import Enum

from django.utils import timezone
from django.db.models import Sum

from django.db import transaction


from .models import (
    Homework,
    Submission,
    Question,
    Answer,
    Course,
    QuestionTypes,
    AnswerTypes,
    Enrollment,
)


logger = logging.getLogger(__name__)


class HomeworkScoringStatus(Enum):
    OK = "OK"
    FAIL = "Warning"


def is_float_equal(
    value1: str, value2: str, tolerance: float = 0.01
) -> bool:
    try:
        return abs(float(value1) - float(value2)) <= tolerance
    except ValueError:
        return False


def is_integer_equal(value1: str, value2: str) -> bool:
    try:
        return int(value1) == int(value2)
    except ValueError:
        return False


def safe_split(value: str, delimiter: str = ","):
    if not value:
        return []

    value = value.strip()
    return value.split(delimiter)


def safe_split_to_int(value: str, delimiter: str = ","):
    raw = safe_split(value, delimiter)
    return [int(x) for x in raw]


def is_multiple_choice_answer_correct(
    question: Question, answer: Answer
) -> bool:
    user_answer = answer.answer_text

    if not user_answer:
        return False

    selected_option = int(user_answer)
    correct_answer = question.get_correct_answer_indices()
    return selected_option in correct_answer


def is_checkbox_answer_correct(
    question: Question, answer: Answer
) -> bool:
    user_answer = answer.answer_text
    selected_options = set(safe_split_to_int(user_answer))
    correct_answer = question.get_correct_answer_indices()
    return selected_options == correct_answer


def is_free_form_answer_correct(
    question: Question, answer: Answer
) -> bool:
    answer_type = question.answer_type

    if answer_type == AnswerTypes.ANY.value:
        return True

    user_answer = answer.answer_text
    user_answer = (user_answer or "").strip().lower()

    correct_answer = question.get_correct_answer()
    correct_answer = (correct_answer or "").strip().lower()

    if answer_type == AnswerTypes.EXACT_STRING.value:
        return user_answer == correct_answer
    elif answer_type == AnswerTypes.CONTAINS_STRING.value:
        return correct_answer in user_answer
    elif answer_type == AnswerTypes.FLOAT.value:
        return is_float_equal(
            user_answer, correct_answer, tolerance=0.01
        )
    elif answer_type == AnswerTypes.INTEGER.value:
        return is_integer_equal(user_answer, correct_answer)

    return False


def is_answer_correct(question: Question, answer: Answer) -> bool:
    if question.answer_type == AnswerTypes.ANY.value:
        return True

    if question.question_type == QuestionTypes.MULTIPLE_CHOICE.value:
        return is_multiple_choice_answer_correct(question, answer)

    if question.question_type == QuestionTypes.CHECKBOXES.value:
        return is_checkbox_answer_correct(question, answer)

    if question.question_type == QuestionTypes.FREE_FORM.value:
        return is_free_form_answer_correct(question, answer)

    return False


def update_score(submission: Submission, save: bool = True):
    logger.info(f"Scoring submission {submission}")
    updated_answers = []
    questions_score = 0

    for answer, question in submission.answers_with_questions:
        is_correct = is_answer_correct(question, answer)

        answer.is_correct = is_correct
        updated_answers.append(answer)
        if save:
            answer.save()

        if is_correct:
            questions_score += question.scores_for_correct_answer

    submission.questions_score = questions_score

    learning_in_public_score = 0

    if submission.learning_in_public_links:
        learning_in_public_score = len(
            submission.learning_in_public_links
        )
        submission.learning_in_public_score = learning_in_public_score

    faq_score = 0

    if (
        submission.faq_contribution
        and len(submission.faq_contribution) >= 5
    ):
        faq_score = 1
        submission.faq_score = faq_score

    total_score = questions_score + learning_in_public_score + faq_score

    submission.total_score = total_score

    if save:
        submission.save()

    return submission, updated_answers


def score_homework_submissions(
    homework_id: str,
) -> tuple[HomeworkScoringStatus, str]:
    with transaction.atomic():
        logger.info(f"Scoring submissions for homework {homework_id}")

        homework = Homework.objects.select_for_update().get(
            pk=homework_id
        )

        if homework.due_date > timezone.now():
            return (
                HomeworkScoringStatus.FAIL,
                f"The due date for {homework} is in the future. Update the due date to score.",
            )

        if homework.is_scored:
            return (
                HomeworkScoringStatus.FAIL,
                f"Homework {homework} is already scored.",
            )

        submissions = Submission.objects.filter(
            homework__id=homework_id
        )

        logger.info(
            f"Scoring {len(submissions)} submissions for {homework}"
        )
        updated_submissions = []
        all_updated_answers = []

        for submission in submissions:
            updated_submission, updated_answers = update_score(
                submission, save=False
            )
            updated_submissions.append(updated_submission)
            all_updated_answers.extend(updated_answers)

        logger.info(
            f"Updating {len(updated_submissions)} submissions for {homework}"
        )

        Submission.objects.bulk_update(
            updated_submissions,
            [
                "questions_score",
                "learning_in_public_score",
                "faq_score",
                "total_score",
            ],
        )

        logger.info(
            f"Updating {len(all_updated_answers)} answers for {homework}"
        )
        Answer.objects.bulk_update(all_updated_answers, ["is_correct"])

        homework.is_scored = True
        homework.save()

        logger.info(
            f"Scored {len(submissions)} submissions for {homework}"
        )

        course = homework.course
        update_leaderboard(course)

        course.first_homework_scored = True
        course.save()

        return (
            HomeworkScoringStatus.OK,
            f"Homework {homework} is scored",
        )


def update_leaderboard(course: Course):
    logger.info(f"Updating leaderboard for course {course}")

    scored_homeworks = Homework.objects.filter(
        course=course, is_scored=True
    )

    logger.info(
        f"Updating scores based on {scored_homeworks.count()} homeworks"
    )

    aggregated_scores = (
        Submission.objects.filter(homework__in=scored_homeworks)
        .values("enrollment")
        .annotate(total_score=Sum("total_score"))
    )

    sorted_scores = sorted(
        aggregated_scores, key=lambda x: x["total_score"], reverse=True
    )

    logger.info(f"Updating {len(aggregated_scores)} enrollments")

    enrollments = Enrollment.objects.filter(course=course)
    enrollments_by_id = {
        enrollment.id: enrollment for enrollment in enrollments
    }

    enrollments_to_update = []

    for rank, score in enumerate(sorted_scores, start=1):
        enrollment_id = score["enrollment"]
        total_score = score["total_score"]

        enrollment = enrollments_by_id[enrollment_id]
        enrollment.total_score = total_score
        enrollment.position_on_leaderboard = rank

        enrollments_to_update.append(enrollment)

    Enrollment.objects.bulk_update(
        enrollments_to_update,
        ["total_score", "position_on_leaderboard"],
    )
