import logging
import statistics

from time import time
from enum import Enum
from dataclasses import dataclass
from collections import defaultdict

from django.utils import timezone
from django.db.models import Sum, Count

from django.db import transaction
from django.core.cache import cache

from .wrapped_statistics import (
    calculate_wrapped_statistics as calculate_wrapped_statistics,
)

from .models import (
    Homework,
    HomeworkState,
    HomeworkStatistics,
    Submission,
    Question,
    Answer,
    Course,
    QuestionTypes,
    AnswerTypes,
    Enrollment,
    Project,
    ProjectSubmission,
    ProjectStatistics,
    ProjectState,
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
    values = []
    for item in raw:
        parsed_item = int(item)
        values.append(parsed_item)
    return values


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


def normalized_free_form_answer(answer_text: str | None) -> str:
    return (answer_text or "").strip()


def is_any_free_form_answer_correct(
    user_answer: str,
    correct_answer: str,
) -> bool:
    return len(user_answer) > 0


def is_exact_string_answer_correct(
    user_answer: str,
    correct_answer: str,
) -> bool:
    return user_answer.lower() == correct_answer.lower()


def is_contains_string_answer_correct(
    user_answer: str,
    correct_answer: str,
) -> bool:
    return correct_answer.lower() in user_answer.lower()


def is_float_answer_correct(
    user_answer: str,
    correct_answer: str,
) -> bool:
    return is_float_equal(user_answer, correct_answer, tolerance=0.01)


def is_integer_answer_correct(
    user_answer: str,
    correct_answer: str,
) -> bool:
    return is_integer_equal(user_answer, correct_answer)


FREE_FORM_ANSWER_CHECKS = {
    AnswerTypes.ANY.value: is_any_free_form_answer_correct,
    AnswerTypes.EXACT_STRING.value: is_exact_string_answer_correct,
    AnswerTypes.CONTAINS_STRING.value: is_contains_string_answer_correct,
    AnswerTypes.FLOAT.value: is_float_answer_correct,
    AnswerTypes.INTEGER.value: is_integer_answer_correct,
}


def is_free_form_answer_correct(
    question: Question, answer: Answer
) -> bool:
    answer_check = FREE_FORM_ANSWER_CHECKS.get(question.answer_type)
    if answer_check is None:
        return False

    user_answer = normalized_free_form_answer(answer.answer_text)
    correct_answer = normalized_free_form_answer(
        question.get_correct_answer()
    )
    return answer_check(user_answer, correct_answer)


QUESTION_ANSWER_CHECKS = {
    QuestionTypes.MULTIPLE_CHOICE.value: is_multiple_choice_answer_correct,
    QuestionTypes.CHECKBOXES.value: is_checkbox_answer_correct,
    QuestionTypes.FREE_FORM.value: is_free_form_answer_correct,
    QuestionTypes.FREE_FORM_LONG.value: is_free_form_answer_correct,
}


def is_answer_correct(question: Question, answer: Answer) -> bool:
    if question.answer_type == AnswerTypes.ANY.value:
        return True

    answer_check = QUESTION_ANSWER_CHECKS.get(question.question_type)
    if answer_check is None:
        return False

    return answer_check(question, answer)


def update_learning_in_public_score(submission: Submission) -> int:
    learning_in_public_score = 0

    # Check if learning in public is disabled for this enrollment
    if submission.enrollment.disable_learning_in_public:
        submission.learning_in_public_score = 0
        return 0

    if submission.learning_in_public_links:
        learning_in_public_score = len(
            submission.learning_in_public_links
        )
        submission.learning_in_public_score = learning_in_public_score

    return learning_in_public_score


def update_faq_score(submission: Submission) -> int:
    faq_score = 0

    if (
        submission.faq_contribution_url
        and len(submission.faq_contribution_url) >= 5
    ):
        faq_score = 1
        submission.faq_score = faq_score

    return faq_score


def _score_answer(submission: Submission, answer: Answer, save: bool) -> int:
    is_correct = is_answer_correct(answer.question, answer)
    answer.is_correct = is_correct
    if save:
        answer.save()

    if is_correct:
        return answer.question.scores_for_correct_answer
    return 0


def _questions_score(
    submission: Submission, answers: list[Answer], save: bool
) -> int:
    score = 0
    for answer in answers:
        answer_score = _score_answer(submission, answer, save)
        score += answer_score
    return score


def _submission_total_score(submission: Submission, questions_score: int):
    lip_score = update_learning_in_public_score(submission)
    faq_score = update_faq_score(submission)
    return questions_score + lip_score + faq_score


def update_score(
    submission: Submission, answers: list[Answer], save: bool = True
) -> None:
    logger.info(f"Scoring submission {submission.id}")
    questions_score = _questions_score(submission, answers, save)
    submission.questions_score = questions_score
    submission.total_score = _submission_total_score(
        submission,
        questions_score,
    )

    if save:
        submission.save()


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
    update_leaderboard(course)

    course.first_homework_scored = True
    course.save()

    calculate_homework_statistics(homework, force=True)


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


def _homework_scores_by_enrollment(course):
    homeworks = Homework.objects.filter(course=course)
    aggregated_homework_scores = (
        Submission.objects.filter(homework__in=homeworks)
        .values("enrollment")
        .annotate(total_score=Sum("total_score"))
    )
    scores_by_enrollment = {}
    for score in aggregated_homework_scores:
        enrollment_id = score["enrollment"]
        scores_by_enrollment[enrollment_id] = score["total_score"]
    return scores_by_enrollment


def _project_scores_by_enrollment(course):
    projects = Project.objects.filter(course=course)
    aggregated_project_scores = (
        ProjectSubmission.objects.filter(
            project__in=projects,
            volunteer_review_only=False,
        )
        .values("enrollment")
        .annotate(total_score=Sum("total_score"))
    )
    scores_by_enrollment = {}
    for score in aggregated_project_scores:
        enrollment_id = score["enrollment"]
        scores_by_enrollment[enrollment_id] = score["total_score"]
    return scores_by_enrollment


def _rank_enrollments(enrollments):
    enrollments = sorted(
        enrollments,
        key=lambda x: (-(x.total_score or 0), x.id),
    )
    for rank, enrollment in enumerate(enrollments, 1):
        enrollment.position_on_leaderboard = rank
    return enrollments


def _update_enrollment_totals(course):
    homework_scores = _homework_scores_by_enrollment(course)
    project_scores = _project_scores_by_enrollment(course)
    enrollments = list(Enrollment.objects.filter(course=course))

    for enrollment in enrollments:
        enrollment.total_score = (
            homework_scores.get(enrollment.id, 0)
            + project_scores.get(enrollment.id, 0)
        )

    enrollments = _rank_enrollments(enrollments)

    Enrollment.objects.bulk_update(
        enrollments,
        ["total_score", "position_on_leaderboard"],
    )


def _invalidate_leaderboard_caches(course):
    cache.delete(f"leaderboard:{course.id}")
    cache.delete(f"leaderboard_data:{course.id}")
    cache.delete(f"leaderboard_yaml:{course.id}")
    version_key = f"leaderboard_cache_version:{course.id}"
    cache.set(version_key, cache.get(version_key, 1) + 1, None)
    logger.info(f"Invalidated cache for leaderboard of course {course.id}")


def update_leaderboard(course: Course):
    t0 = time()
    logger.info(f"Updating leaderboard for course {course.id}")
    _update_enrollment_totals(course)
    _invalidate_leaderboard_caches(course)
    t1 = time()
    logger.info(f"Updated leaderboard in {(t1 - t0):.2f} seconds")


def fill_most_common_answer_as_correct(question: Question) -> None:
    if question.correct_answer and not has_invalid_correct_answer_indices(question):
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
    return Question.objects.filter(homework=homework).update(correct_answer="")


HOMEWORK_STAT_FIELDS = [
    "questions_score",
    "learning_in_public_score",
    "total_score",
    "time_spent_lectures",
    "time_spent_homework",
]

PROJECT_STAT_FIELDS = [
    "project_score",
    "project_learning_in_public_score",
    "peer_review_score",
    "peer_review_learning_in_public_score",
    "total_score",
    "time_spent",
]


def _empty_field_distribution():
    return {
        "min": None,
        "max": None,
        "avg": None,
        "q1": None,
        "median": None,
        "q3": None,
    }


def _field_values(submissions_data, field):
    values = []
    for submission in submissions_data:
        value = submission[field]
        if value is not None:
            values.append(value)
    return values


def _field_distribution(values):
    if len(values) < 3:
        return _empty_field_distribution()

    quantiles = statistics.quantiles(values, n=4, method="inclusive")
    return {
        "min": min(values),
        "max": max(values),
        "avg": statistics.mean(values),
        "q1": quantiles[0],
        "median": quantiles[1],
        "q3": quantiles[2],
    }


def _calculate_field_distributions(submissions_data, fields):
    """Compute min/max/avg/quantiles per field from prefetched submission rows."""
    stats = {"total_submissions": len(submissions_data)}

    for field in fields:
        stats[field] = _field_distribution(
            _field_values(submissions_data, field)
        )

    return stats


def _persist_field_stats(stats, calculated_stats, fields):
    """Copy the computed distribution for each field onto a stats model instance."""
    stats.total_submissions = calculated_stats["total_submissions"]

    for field in fields:
        field_stats = calculated_stats[field]

        setattr(stats, f"min_{field}", field_stats["min"])
        setattr(stats, f"max_{field}", field_stats["max"])
        setattr(stats, f"avg_{field}", field_stats["avg"])
        setattr(stats, f"median_{field}", field_stats["median"])
        setattr(stats, f"q1_{field}", field_stats["q1"])
        setattr(stats, f"q3_{field}", field_stats["q3"])


def calculate_raw_homework_statistics(homework):
    # Single query to get all the fields we need, avoiding the N+1 problem
    submissions_data = list(
        Submission.objects.filter(homework=homework).values(
            *HOMEWORK_STAT_FIELDS
        )
    )
    return _calculate_field_distributions(
        submissions_data, HOMEWORK_STAT_FIELDS
    )


def calculate_homework_statistics(homework, force=False):
    if homework.state != HomeworkState.SCORED.value:
        raise ValueError(
            f"Cannot calculate statistics for unscored homework {homework}"
        )

    stats, created = HomeworkStatistics.objects.get_or_create(
        homework=homework
    )

    if force or created:
        calculated_stats = calculate_raw_homework_statistics(homework)
        _persist_field_stats(
            stats, calculated_stats, HOMEWORK_STAT_FIELDS
        )
        stats.save()

    return stats


def calculate_raw_project_statistics(project):
    # Single query to get all the fields we need, avoiding the N+1 problem
    submissions_data = list(
        ProjectSubmission.objects.filter(project=project).values(
            *PROJECT_STAT_FIELDS
        )
    )
    return _calculate_field_distributions(
        submissions_data, PROJECT_STAT_FIELDS
    )


def calculate_project_statistics(project, force=False):
    if project.state != ProjectState.COMPLETED.value:
        raise ValueError(
            f"Cannot calculate statistics for uncompleted project {project}"
        )

    stats, created = ProjectStatistics.objects.get_or_create(
        project=project
    )

    if force or created:
        calculated_stats = calculate_raw_project_statistics(project)
        _persist_field_stats(
            stats, calculated_stats, PROJECT_STAT_FIELDS
        )
        stats.save()

    return stats
