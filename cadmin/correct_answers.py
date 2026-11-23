"""Validation and persistence for correct answers edited in cadmin."""

from courses.models.homework import Question


class CorrectAnswerError(ValueError):
    """The submitted correct answer cannot be stored for this question."""


_UNSET = object()


def _valid_answer_types():
    answer_types = set()
    for value, _label in Question.ANSWER_TYPES:
        answer_types.add(value)
    return answer_types


def normalize_choice_answer(question, values):
    """Turn submitted option numbers into the stored "1,3" format.

    Blank values are dropped: browsers send a hidden empty field alongside
    checkboxes, and an empty selection legitimately means "no answer".
    """
    if isinstance(values, (str, int)):
        values = [values]
    if not isinstance(values, (list, tuple)):
        raise CorrectAnswerError("Choice answers must be a list of options")

    option_count = len(question.get_possible_answers())
    indices = set()
    for raw in values:
        token = str(raw).strip()
        if not token:
            continue
        try:
            index = int(token)
        except ValueError as exc:
            raise CorrectAnswerError(
                f"Option {token!r} is not a number"
            ) from exc
        if index < 1 or index > option_count:
            raise CorrectAnswerError(
                f"Option {index} is out of range 1..{option_count}"
            )
        indices.add(index)

    parts = []
    for index in sorted(indices):
        parts.append(str(index))
    return ",".join(parts)


def normalize_free_text_answer(value):
    if value is None:
        return ""
    if not isinstance(value, (str, int, float)):
        raise CorrectAnswerError("Free-text answer must be a string")
    return str(value).strip()


def normalize_answer_type(value):
    if value in (None, ""):
        return None
    if value not in _valid_answer_types():
        raise CorrectAnswerError(f"Unknown answer type {value!r}")
    return value


def save_question_correct_answer(question, correct_answer, answer_type=_UNSET):
    """Validate and store one question's correct answer.

    ``answer_type`` is only changed when it is passed, so a checkbox click
    never resets a free-text question's type.
    """
    update_fields = ["correct_answer"]
    if question.has_choice_answers():
        question.correct_answer = normalize_choice_answer(
            question, correct_answer
        )
    else:
        question.correct_answer = normalize_free_text_answer(correct_answer)

    if answer_type is not _UNSET:
        question.answer_type = normalize_answer_type(answer_type)
        update_fields.append("answer_type")

    question.save(update_fields=update_fields)
    return question
