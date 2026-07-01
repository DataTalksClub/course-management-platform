from courses.models.homework import (
    Answer,
    AnswerTypes,
    Question,
    QuestionTypes,
)


def is_float_equal(
    value1: str, value2: str, tolerance: float = 0.01
) -> bool:
    try:
        number1 = float(value1)
        number2 = float(value2)
    except ValueError:
        return False
    difference = abs(number1 - number2)
    return difference <= tolerance


def is_integer_equal(value1: str, value2: str) -> bool:
    try:
        number1 = int(value1)
        number2 = int(value2)
    except ValueError:
        return False
    return number1 == number2


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
    selected_option_values = safe_split_to_int(user_answer)
    selected_options = set(selected_option_values)
    correct_answer = question.get_correct_answer_indices()
    return selected_options == correct_answer


def normalized_free_form_answer(answer_text: str | None) -> str:
    answer_value = answer_text or ""
    normalized_answer = answer_value.strip()
    return normalized_answer


def is_any_free_form_answer_correct(
    user_answer: str,
    correct_answer: str,
) -> bool:
    return len(user_answer) > 0


def is_exact_string_answer_correct(
    user_answer: str,
    correct_answer: str,
) -> bool:
    normalized_user_answer = user_answer.lower()
    normalized_correct_answer = correct_answer.lower()
    return normalized_user_answer == normalized_correct_answer


def is_contains_string_answer_correct(
    user_answer: str,
    correct_answer: str,
) -> bool:
    normalized_user_answer = user_answer.lower()
    normalized_correct_answer = correct_answer.lower()
    return normalized_correct_answer in normalized_user_answer


FREE_FORM_ANSWER_CHECKS = {
    AnswerTypes.ANY.value: is_any_free_form_answer_correct,
    AnswerTypes.EXACT_STRING.value: is_exact_string_answer_correct,
    AnswerTypes.CONTAINS_STRING.value: is_contains_string_answer_correct,
    AnswerTypes.FLOAT.value: is_float_equal,
    AnswerTypes.INTEGER.value: is_integer_equal,
}


def is_free_form_answer_correct(
    question: Question, answer: Answer
) -> bool:
    answer_check = FREE_FORM_ANSWER_CHECKS.get(question.answer_type)
    if answer_check is None:
        return False

    user_answer = normalized_free_form_answer(answer.answer_text)
    raw_correct_answer = question.get_correct_answer()
    correct_answer = normalized_free_form_answer(raw_correct_answer)
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
