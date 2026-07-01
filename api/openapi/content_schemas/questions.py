from courses.models.homework import Question

from ..primitives import JSON, array_of, model_properties, ref


QUESTION_REF = ref("Question")
QUESTION_ARRAY = array_of(QUESTION_REF)
QUESTION_CREATE_REF = ref("QuestionCreate")
QUESTION_CREATE_ARRAY = array_of(QUESTION_CREATE_REF)
QUESTION_TEXT_PROPERTIES = model_properties(Question, ["id", "text"])
QUESTION_CREATE_TEXT_PROPERTIES = model_properties(Question, ["text"])
QUESTION_ANSWER_PROPERTIES = model_properties(
    Question,
    ["correct_answer", "scores_for_correct_answer"],
)
QUESTION_TYPE_REF = ref("QuestionType")
ANSWER_TYPE_REF = ref("AnswerType")
STRING_SCHEMA = {"type": "string"}
POSSIBLE_ANSWERS_ARRAY = array_of(STRING_SCHEMA)
DELETE_BLOCKERS_ARRAY = array_of(STRING_SCHEMA)
ERROR_ARRAY = array_of(JSON)
QUESTION_CREATE_INLINE_ALLOF = [QUESTION_CREATE_REF]

QUESTION_SCHEMAS = {
    "Question": {
        "type": "object",
        "properties": {
            **QUESTION_TEXT_PROPERTIES,
            "question_type": QUESTION_TYPE_REF,
            "answer_type": ANSWER_TYPE_REF,
            "possible_answers": POSSIBLE_ANSWERS_ARRAY,
            **QUESTION_ANSWER_PROPERTIES,
            "answers_count": {"type": "integer"},
            "can_delete": {"type": "boolean"},
            "delete_blockers": DELETE_BLOCKERS_ARRAY,
        },
    },
    "QuestionsList": {
        "type": "object",
        "required": ["homework_id", "homework_title", "questions"],
        "properties": {
            "homework_id": {"type": "integer"},
            "homework_title": {"type": "string"},
            "questions": QUESTION_ARRAY,
        },
    },
    "QuestionCreate": {
        "type": "object",
        "required": ["text"],
        "properties": {
            **QUESTION_CREATE_TEXT_PROPERTIES,
            "question_type": QUESTION_TYPE_REF,
            "answer_type": ANSWER_TYPE_REF,
            "possible_answers": POSSIBLE_ANSWERS_ARRAY,
            **QUESTION_ANSWER_PROPERTIES,
        },
    },
    "QuestionCreateInline": {
        "allOf": QUESTION_CREATE_INLINE_ALLOF,
        "description": (
            "Question payload accepted while creating a homework. The current "
            "implementation does not require text for inline questions."
        ),
    },
    "QuestionCreateRequest": {
        "oneOf": [
            QUESTION_CREATE_REF,
            QUESTION_CREATE_ARRAY,
        ],
    },
    "QuestionCreateResponse": {
        "type": "object",
        "required": ["created"],
        "properties": {
            "created": QUESTION_ARRAY,
            "errors": ERROR_ARRAY,
        },
    },
    "QuestionPatch": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            **QUESTION_CREATE_TEXT_PROPERTIES,
            "question_type": QUESTION_TYPE_REF,
            "answer_type": ANSWER_TYPE_REF,
            "possible_answers": POSSIBLE_ANSWERS_ARRAY,
            **QUESTION_ANSWER_PROPERTIES,
        },
    }
}
