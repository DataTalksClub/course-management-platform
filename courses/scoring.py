import logging

from time import time
from enum import Enum
from collections import defaultdict

from django.utils import timezone
from django.db.models import Sum, Count

from django.db import transaction


from .models import (
    Homework,
    HomeworkState,
    Submission,
    Question,
    Answer,
    Course,
    QuestionTypes,
    AnswerTypes,
    Enrollment,
    Project,
    ProjectSubmission,
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


def update_score(
    submission: Submission, answers: list[Answer], save: bool = True
) -> None:
    logger.info(f"Scoring submission {submission.id}")
    questions_score = 0

    for answer in answers:
        question = answer.question
        try:
            is_correct = is_answer_correct(question, answer)
        except Exception as e:
            logger.exception(
                f"Error while scoring submission {submission.id}"
            )
            raise e
            # is_correct = False

        answer.is_correct = is_correct
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


def score_homework_submissions(
    homework_id: str,
) -> tuple[HomeworkScoringStatus, str]:
    with transaction.atomic():
        t0 = time()
        logger.info(f"Scoring submissions for homework {homework_id}")

        homework = Homework.objects.get(pk=homework_id)

        if homework.due_date > timezone.now():
            return (
                HomeworkScoringStatus.FAIL,
                f"The due date for {homework_id} is in the future. Update the due date to score.",
            )

        if homework.state == HomeworkState.CLOSED.value:
            return (
                HomeworkScoringStatus.FAIL,
                f"Homework {homework_id} is closed. Update the state to OPEN to score.",
            )

        if homework.state == HomeworkState.SCORED.value:
            return (
                HomeworkScoringStatus.FAIL,
                f"Homework {homework_id} is already scored.",
            )

        submissions = Submission.objects.filter(
            homework__id=homework_id
        )
        answers = Answer.objects.filter(
            submission__in=submissions
        ).select_related("question", "submission")

        answers_by_submission_id = defaultdict(list)
        for answer in answers:
            aid = answer.submission_id
            answers_by_submission_id[aid].append(answer)

        logger.info(
            f"Scoring {len(answers_by_submission_id)} submissions for homework {homework_id}"
        )

        for submission in submissions:
            submission_answers = answers_by_submission_id[submission.id]
            update_score(submission, submission_answers, save=False)

        logger.info(
            f"Updating the submissions for homework {homework_id}"
        )

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

        homework.state = HomeworkState.SCORED.value
        homework.save()

        logger.info(
            f"Scored {len(submissions)} submissions for homework {homework_id}"
        )

        course = homework.course
        update_leaderboard(course)

        course.first_homework_scored = True
        course.save()

        t1 = time()
        logger.info(f"Scored homework in {(t1 - t0):.2f} seconds")
        return (
            HomeworkScoringStatus.OK,
            f"Homework {homework_id} is scored",
        )


def update_leaderboard(course: Course):
    t0 = time()
    logger.info(f"Updating leaderboard for course {course.id}")

    homeworks = Homework.objects.filter(course=course)

    aggregated_homework_scores = (
        Submission.objects.filter(homework__in=homeworks)
        .values("enrollment")
        .annotate(total_score=Sum("total_score"))
    )
    homework_scores_by_enrollment = {
        score["enrollment"]: score["total_score"]
        for score in aggregated_homework_scores
    }

    projects = Project.objects.filter(course=course)

    aggregated_project_scores = (
        ProjectSubmission.objects.filter(project__in=projects)
        .values("enrollment")
        .annotate(total_score=Sum("total_score"))
    )

    project_score_by_enrollment = {
        score["enrollment"]: score["total_score"]
        for score in aggregated_project_scores
    }

    enrollments = list(Enrollment.objects.filter(course=course))

    for enrollment in enrollments:
        homework_score = homework_scores_by_enrollment.get(
            enrollment.id, 0
        )
        project_score = project_score_by_enrollment.get(
            enrollment.id, 0
        )

        enrollment.total_score = homework_score + project_score

    enrollments = sorted(
        enrollments, key=lambda x: x.total_score, reverse=True
    )

    for rank, enrollment in enumerate(enrollments, 1):
        enrollment.position_on_leaderboard = rank

    Enrollment.objects.bulk_update(
        enrollments,
        ["total_score", "position_on_leaderboard"],
    )

    t1 = time()
    logger.info(f"Updated leaderboard in {(t1 - t0):.2f} seconds")


def fill_most_common_answer_as_correct(question: Question) -> None:
    if question.correct_answer:
        logger.info(f"Correct answer for {question} is already set")
        return

    most_common_answer = (
        Answer.objects.filter(
            question=question,
            answer_text__isnull=False,
            answer_text__gt="",
        )
        .values("answer_text")
        .annotate(count=Count("answer_text"))
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


def fill_correct_answers(homework: Homework) -> None:
    questions = Question.objects.filter(homework=homework)

    for question in questions:
        fill_most_common_answer_as_correct(question)
