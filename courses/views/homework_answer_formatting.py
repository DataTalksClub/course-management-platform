from courses.models.homework import Question


def _selected_option_index(option: str) -> int | None:
    option = option.strip()
    if not option:
        return None

    try:
        return int(option)
    except ValueError:
        return None


def _selected_option_indexes(answer_text: str | None):
    raw_answer_text = answer_text or ""
    stripped_answer_text = raw_answer_text.strip()
    options = stripped_answer_text.split(",")
    for option in options:
        index = _selected_option_index(option)
        if index is not None:
            yield index


def extract_selected_option_indexes(
    answer_text: str | None,
) -> list[int]:
    indexes = []
    selected_option_indexes = _selected_option_indexes(answer_text)
    for index in selected_option_indexes:
        indexes.append(index)
    return indexes


def format_hours(value: float | None) -> str:
    if value is None:
        return ""

    return f"{value:g} hours"


def format_submitted_value(value: str) -> str:
    if value:
        return value
    return "Not submitted"


def format_selected_answer(
    question: Question,
    answer_text: str | None,
) -> str:
    selected_indexes = extract_selected_option_indexes(answer_text)
    possible_answers = question.get_possible_answers()
    selected_options = []
    for index in selected_indexes:
        option = selected_option_label(possible_answers, index)
        selected_options.append(option)
    return ", ".join(selected_options)


def selected_option_value(
    possible_answers: list[str],
    index: int,
) -> str:
    if 1 <= index <= len(possible_answers):
        return possible_answers[index - 1]
    return ""


def selected_option_label(
    possible_answers: list[str],
    index: int,
) -> str:
    value = selected_option_value(possible_answers, index)
    if value:
        return f"{index}. {value}"
    return str(index)
