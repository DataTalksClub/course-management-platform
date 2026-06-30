from dataclasses import dataclass
from typing import List, Optional

from courses.models import Answer, Homework, HomeworkState, Question
from courses.models import QuestionTypes
from courses.scoring import is_free_form_answer_correct


CHOICE_QUESTION_TYPES = {
    QuestionTypes.MULTIPLE_CHOICE.value,
    QuestionTypes.CHECKBOXES.value,
}
FREE_FORM_QUESTION_TYPES = {
    QuestionTypes.FREE_FORM.value,
    QuestionTypes.FREE_FORM_LONG.value,
}


@dataclass(frozen=True)
class ChoiceOptionData:
    homework: Homework
    option: str
    index: int
    selected_options: list[int]
    correct_indices: list[int]


@dataclass(frozen=True)
class AnswerClassState:
    selected: bool
    correct: bool


def process_unscored_free_form_answer(answer: Optional[Answer]):
    if not answer:
        return {"text": ""}

    return {"text": answer.answer_text}


def free_form_answer_missing(answer: Optional[Answer]) -> bool:
    return (
        not answer
        or not answer.answer_text
        or not answer.answer_text.strip()
    )


def process_missing_scored_free_form_answer(question: Question):
    return {
        "text": question.correct_answer,
        "no_answer_submitted": True,
    }


def process_scored_free_form_answer(
    question: Question, answer: Optional[Answer]
):
    if free_form_answer_missing(answer):
        return process_missing_scored_free_form_answer(question)

    answer_is_correct = is_free_form_answer_correct(question, answer)
    correctly_selected_class = "option-answer-correct"
    if not answer_is_correct:
        correctly_selected_class = "option-answer-incorrect"

    return {
        "text": answer.answer_text,
        "correctly_selected_class": correctly_selected_class,
    }


def process_question_free_form(
    homework: Homework, question: Question, answer: Optional[Answer]
):
    if not homework.is_scored():
        return process_unscored_free_form_answer(answer)

    return process_scored_free_form_answer(question, answer)


def process_question_options_multiple_choice_or_checkboxes(
    homework: Homework, question: Question, answer: Optional[Answer]
):
    selected_options = extract_selected_options(answer)
    possible_answers = question.get_possible_answers()
    correct_indices = (
        question.get_correct_answer_indices()
        if homework.is_scored()
        else []
    )

    options = []
    for index, option in enumerate(possible_answers, start=1):
        option_data = ChoiceOptionData(
            homework=homework,
            option=option,
            index=index,
            selected_options=selected_options,
            correct_indices=correct_indices,
        )
        processed_option = process_choice_option(option_data)
        options.append(processed_option)

    result = {"options": options}
    if no_choice_answer_submitted(homework, selected_options):
        result["no_answer_submitted"] = True

    return result


def process_choice_option(data: ChoiceOptionData):
    is_selected = data.index in data.selected_options
    processed_answer = {
        "value": data.option,
        "is_selected": is_selected,
        "index": data.index,
    }

    if data.homework.state == HomeworkState.SCORED.value:
        is_correct = data.index in data.correct_indices
        answer_class_state = AnswerClassState(
            selected=is_selected,
            correct=is_correct,
        )
        correctly_selected_class = determine_answer_class(
            answer_class_state
        )
        processed_answer.update(
            {
                "is_correct": is_correct,
                "correctly_selected_class": correctly_selected_class,
            }
        )

    return processed_answer


def no_choice_answer_submitted(
    homework: Homework,
    selected_options: list[int],
) -> bool:
    return homework.is_scored() and len(selected_options) == 0


def extract_selected_options(answer):
    if not answer:
        return []

    return extract_selected_option_indexes(answer.answer_text)


def _selected_option_index(option: str) -> Optional[int]:
    option = option.strip()
    if not option:
        return None

    try:
        return int(option)
    except ValueError:
        return None


def _selected_option_indexes(answer_text: Optional[str]):
    options = (answer_text or "").strip().split(",")
    for option in options:
        index = _selected_option_index(option)
        if index is not None:
            yield index


def extract_selected_option_indexes(
    answer_text: Optional[str],
) -> List[int]:
    indexes = []
    selected_option_indexes = _selected_option_indexes(answer_text)
    for index in selected_option_indexes:
        indexes.append(index)
    return indexes


def format_hours(value: Optional[float]) -> str:
    if value is None:
        return ""

    return f"{value:g} hours"


def format_submitted_value(value: str) -> str:
    return value if value else "Not submitted"


def format_selected_answer(
    question: Question,
    answer_text: Optional[str],
) -> str:
    selected_indexes = extract_selected_option_indexes(answer_text)
    possible_answers = question.get_possible_answers()
    selected_options = []
    for index in selected_indexes:
        option = selected_option_label(possible_answers, index)
        selected_options.append(option)
    return ", ".join(selected_options)


def selected_option_value(
    possible_answers: List[str],
    index: int,
) -> str:
    if 1 <= index <= len(possible_answers):
        return possible_answers[index - 1]
    return ""


def selected_option_label(
    possible_answers: List[str],
    index: int,
) -> str:
    value = selected_option_value(possible_answers, index)
    if value:
        return f"{index}. {value}"
    return str(index)


def determine_answer_class(state: AnswerClassState) -> str:
    if state.correct:
        return "option-answer-correct"
    if state.selected:
        return "option-answer-incorrect"
    return "option-answer-none"


def process_question_options(
    homework: Homework, question: Question, answer: Answer
):
    if question.question_type in FREE_FORM_QUESTION_TYPES:
        return process_question_free_form(homework, question, answer)

    return process_question_options_multiple_choice_or_checkboxes(
        homework, question, answer
    )
