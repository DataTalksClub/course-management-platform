from courses.models.homework import Homework

from ..primitives import (
    JSON,
    array_of,
    model_object_schema,
    model_properties,
    ref,
)


HOMEWORK_REF = ref("Homework")
HOMEWORK_ARRAY = array_of(HOMEWORK_REF)
HOMEWORK_SUMMARY_REF = ref("HomeworkSummary")
HOMEWORK_CREATE_REF = ref("HomeworkCreate")
HOMEWORK_CREATE_ARRAY = array_of(HOMEWORK_CREATE_REF)
QUESTION_CREATE_INLINE_REF = ref("QuestionCreateInline")
QUESTION_CREATE_INLINE_ARRAY = array_of(QUESTION_CREATE_INLINE_REF)
HOMEWORK_STATE_REF = ref("HomeworkState")
STRING_SCHEMA = {"type": "string"}
DELETE_BLOCKERS_ARRAY = array_of(STRING_SCHEMA)
ERROR_ARRAY = array_of(JSON)
HOMEWORK_SUMMARY_SCHEMA = model_object_schema(
    Homework,
    [
        "id",
        "slug",
        "title",
        "instructions_url",
        "due_date",
        "state",
    ],
)
HOMEWORK_DETAIL_MODEL_PROPERTIES = model_properties(
    Homework,
    [
        "description",
        "instructions_url",
        "learning_in_public_cap",
        "homework_url_field",
        "time_spent_lectures_field",
        "time_spent_homework_field",
        "faq_contribution_field",
    ],
)
HOMEWORK_DETAIL_EXTENSION_SCHEMA = {
    "type": "object",
    "properties": {
        **HOMEWORK_DETAIL_MODEL_PROPERTIES,
        "questions_count": {"type": "integer"},
        "submissions_count": {"type": "integer"},
        "can_delete": {"type": "boolean"},
        "delete_blockers": DELETE_BLOCKERS_ARRAY,
    },
}
HOMEWORK_DETAIL_ALLOF = [
    HOMEWORK_SUMMARY_REF,
    HOMEWORK_DETAIL_EXTENSION_SCHEMA,
]
HOMEWORK_DATE_CONTENT_PROPERTIES = model_properties(
    Homework,
    ["due_date", "description", "instructions_url"],
)
HOMEWORK_OPTION_PROPERTIES = model_properties(
    Homework,
    [
        "learning_in_public_cap",
        "homework_url_field",
        "time_spent_lectures_field",
        "time_spent_homework_field",
        "faq_contribution_field",
    ],
)
HOMEWORK_PATCH_BASE_PROPERTIES = model_properties(
    Homework,
    [
        "title",
        "description",
        "instructions_url",
        "due_date",
    ],
)
HOMEWORK_CREATE_REQUEST_ONE_OF = [
    HOMEWORK_CREATE_REF,
    HOMEWORK_CREATE_ARRAY,
]

HOMEWORK_SCHEMAS = {
    "HomeworkSummary": HOMEWORK_SUMMARY_SCHEMA,
    "Homework": {
        "allOf": HOMEWORK_DETAIL_ALLOF,
    },
    "HomeworksList": {
        "type": "object",
        "required": ["homeworks"],
        "properties": {"homeworks": HOMEWORK_ARRAY},
    },
    "HomeworkCreate": {
        "type": "object",
        "required": ["name", "due_date"],
        "properties": {
            "name": {"type": "string"},
            "slug": {"type": "string"},
            **HOMEWORK_DATE_CONTENT_PROPERTIES,
            "questions": QUESTION_CREATE_INLINE_ARRAY,
        },
    },
    "HomeworkCreateRequest": {
        "oneOf": HOMEWORK_CREATE_REQUEST_ONE_OF,
    },
    "HomeworkUpsert": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "title": {"type": "string"},
            **HOMEWORK_DATE_CONTENT_PROPERTIES,
            "state": HOMEWORK_STATE_REF,
            **HOMEWORK_OPTION_PROPERTIES,
            "questions": QUESTION_CREATE_INLINE_ARRAY,
        },
        "description": (
            "Idempotent homework payload. Creating requires name/title and "
            "due_date. If questions are included for an existing homework, "
            "they replace current questions only when the homework is closed "
            "and has no submissions."
        ),
    },
    "HomeworkCreateResponse": {
        "type": "object",
        "required": ["created"],
        "properties": {
            "created": HOMEWORK_ARRAY,
            "errors": ERROR_ARRAY,
        },
    },
    "HomeworkPatch": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            **HOMEWORK_PATCH_BASE_PROPERTIES,
            "state": HOMEWORK_STATE_REF,
            **HOMEWORK_OPTION_PROPERTIES,
        },
    },
    "HomeworkScoreResponse": {
        "type": "object",
        "required": [
            "status",
            "message",
            "homework_id",
            "homework_slug",
            "state",
            "submissions_count",
            "rescored_submissions_count",
        ],
        "properties": {
            "status": {"type": "string", "enum": ["OK", "FAIL"]},
            "message": {"type": "string"},
            "homework_id": {"type": "integer"},
            "homework_slug": {"type": "string"},
            "state": HOMEWORK_STATE_REF,
            "submissions_count": {"type": "integer"},
            "rescored_submissions_count": {"type": "integer"},
        },
    }
}
