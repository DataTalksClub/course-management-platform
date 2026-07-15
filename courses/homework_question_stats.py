from collections import Counter
from dataclasses import dataclass


from courses.models.homework import (
    Answer,
    Homework,
    Question,
)
from courses.views.homework_answer_formatting import (
    extract_selected_option_indexes,
)


@dataclass(frozen=True)
class ChoiceOptionStat:
    index: int
    label: str
    count: int
    pct: float
    is_correct: bool


@dataclass(frozen=True)
class QuestionStat:
    question_id: int
    text: str
    question_type: str
    answer_type: str | None
    correct: int
    total: int
    pct_correct: float | None
    choice_options: list[ChoiceOptionStat] | None
    free_form_values: list[tuple[str, int]] | None


def homework_question_stats(homework: Homework) -> list[QuestionStat]:
    questions = list(
        Question.objects.filter(homework=homework).order_by("id")
    )
    answers = list(
        Answer.objects.filter(question__homework=homework).select_related(
            "question"
        )
    )
    answers_by_question: dict[int, list[Answer]] = {}
    for answer in answers:
        answers_by_question.setdefault(answer.question_id, []).append(answer)

    stats = []
    for question in questions:
        question_answers = answers_by_question.get(question.id, [])
        stat = _build_question_stat(question, question_answers)
        stats.append(stat)
    return stats


def _build_question_stat(
    question: Question, answers: list[Answer]
) -> QuestionStat:
    total = len(answers)
    correct = sum(1 for a in answers if a.is_correct)
    pct_correct = round(correct / total * 100, 1) if total else None

    if question.has_choice_answers():
        choice_options = _choice_distribution(question, answers)
        free_form_values = None
    else:
        choice_options = None
        free_form_values = _free_form_distribution(answers)

    return QuestionStat(
        question_id=question.id,
        text=question.text,
        question_type=question.question_type,
        answer_type=question.answer_type,
        correct=correct,
        total=total,
        pct_correct=pct_correct,
        choice_options=choice_options,
        free_form_values=free_form_values,
    )


def _choice_distribution(
    question: Question, answers: list[Answer]
) -> list[ChoiceOptionStat]:
    possible_answers = question.get_possible_answers()
    correct_indices = question.get_correct_answer_indices()
    total = len(answers)

    option_counter: Counter = Counter()
    for answer in answers:
        selected = extract_selected_option_indexes(answer.answer_text)
        for index in selected:
            option_counter[index] += 1

    options = []
    for index in range(1, len(possible_answers) + 1):
        label = possible_answers[index - 1]
        count = option_counter.get(index, 0)
        pct = round(count / total * 100, 1) if total else 0.0
        is_correct = index in correct_indices
        options.append(
            ChoiceOptionStat(
                index=index,
                label=label,
                count=count,
                pct=pct,
                is_correct=is_correct,
            )
        )
    return options


def _free_form_distribution(
    answers: list[Answer]
) -> list[tuple[str, int]]:
    value_counter: Counter = Counter()
    for answer in answers:
        text = (answer.answer_text or "").strip()
        if text:
            value_counter[text] += 1
    return value_counter.most_common()
