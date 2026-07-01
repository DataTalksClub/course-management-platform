import logging

from django.db.models import Count

from courses.models.homework import (
    Answer,
    Homework,
    Question,
    QuestionTypes,
)


logger = logging.getLogger(__name__)


def fill_most_common_answer_as_correct(question: Question) -> None:
    if question.correct_answer and not has_invalid_correct_answer_indices(
        question
    ):
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
