from dataclasses import dataclass

from courses.models.homework import (
    Answer,
    Homework,
    HomeworkState,
    Question,
    QuestionTypes,
)
from courses.homework_answer_checks import is_free_form_answer_correct
from courses.views.homework_answer_formatting import (
    extract_selected_option_indexes,
)


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


def process_unscored_free_form_answer(answer: Answer | None):
    if not answer:
        return {"text": ""}

    return {"text": answer.answer_text}


def free_form_answer_missing(answer: Answer | None) -> bool:
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
    question: Question, answer: Answer | None
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
    homework: Homework, question: Question, answer: Answer | None
):
    if not homework.is_scored():
        return process_unscored_free_form_answer(answer)

    return process_scored_free_form_answer(question, answer)


def process_question_options_multiple_choice_or_checkboxes(
    homework: Homework, question: Question, answer: Answer | None
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
        correctly_selected_class = determine_answer_class(
            selected=is_selected,
            correct=is_correct,
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
    homework_is_scored = homework.is_scored()
    no_options_selected = len(selected_options) == 0
    return homework_is_scored and no_options_selected


def extract_selected_options(answer):
    if not answer:
        return []

    return extract_selected_option_indexes(answer.answer_text)


def determine_answer_class(*, selected: bool, correct: bool) -> str:
    if correct:
        return "option-answer-correct"
    if selected:
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
