from courses.models import Question

from ..primitives import JSON, array_of, model_properties, ref


QUESTION_SCHEMAS = {
    "Question": {
        "type": "object",
        "properties": {
            **model_properties(Question, ["id", "text"]),
            "question_type": ref("QuestionType"),
            "answer_type": ref("AnswerType"),
            "possible_answers": array_of({"type": "string"}),
            **model_properties(
                Question,
                ["correct_answer", "scores_for_correct_answer"],
            ),
            "answers_count": {"type": "integer"},
            "can_delete": {"type": "boolean"},
            "delete_blockers": array_of({"type": "string"}),
        },
    },
    "QuestionsList": {
        "type": "object",
        "required": ["homework_id", "homework_title", "questions"],
        "properties": {
            "homework_id": {"type": "integer"},
            "homework_title": {"type": "string"},
            "questions": array_of(ref("Question")),
        },
    },
    "QuestionCreate": {
        "type": "object",
        "required": ["text"],
        "properties": {
            **model_properties(Question, ["text"]),
            "question_type": ref("QuestionType"),
            "answer_type": ref("AnswerType"),
            "possible_answers": array_of({"type": "string"}),
            **model_properties(
                Question,
                ["correct_answer", "scores_for_correct_answer"],
            ),
        },
    },
    "QuestionCreateInline": {
        "allOf": [ref("QuestionCreate")],
        "description": (
            "Question payload accepted while creating a homework. The current "
            "implementation does not require text for inline questions."
        ),
    },
    "QuestionCreateRequest": {
        "oneOf": [
            ref("QuestionCreate"),
            array_of(ref("QuestionCreate")),
        ],
    },
    "QuestionCreateResponse": {
        "type": "object",
        "required": ["created"],
        "properties": {
            "created": array_of(ref("Question")),
            "errors": array_of(JSON),
        },
    },
    "QuestionPatch": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            **model_properties(Question, ["text"]),
            "question_type": ref("QuestionType"),
            "answer_type": ref("AnswerType"),
            "possible_answers": array_of({"type": "string"}),
            **model_properties(
                Question,
                ["correct_answer", "scores_for_correct_answer"],
            ),
        },
    }
}
