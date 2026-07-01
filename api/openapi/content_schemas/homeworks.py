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
HOMEWORK_CREATE_REF = ref("HomeworkCreate")
HOMEWORK_CREATE_ARRAY = array_of(HOMEWORK_CREATE_REF)
QUESTION_CREATE_INLINE_REF = ref("QuestionCreateInline")
QUESTION_CREATE_INLINE_ARRAY = array_of(QUESTION_CREATE_INLINE_REF)

HOMEWORK_SCHEMAS = {
    "HomeworkSummary": model_object_schema(
        Homework,
        [
            "id",
            "slug",
            "title",
            "instructions_url",
            "due_date",
            "state",
        ],
    ),
    "Homework": {
        "allOf": [
            ref("HomeworkSummary"),
            {
                "type": "object",
                "properties": {
                    **model_properties(
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
                    ),
                    "questions_count": {"type": "integer"},
                    "submissions_count": {"type": "integer"},
                    "can_delete": {"type": "boolean"},
                    "delete_blockers": array_of({"type": "string"}),
                },
            },
        ],
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
            **model_properties(
                Homework,
                ["due_date", "description", "instructions_url"],
            ),
            "questions": QUESTION_CREATE_INLINE_ARRAY,
        },
    },
    "HomeworkCreateRequest": {
        "oneOf": [
            ref("HomeworkCreate"),
            HOMEWORK_CREATE_ARRAY,
        ],
    },
    "HomeworkUpsert": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "title": {"type": "string"},
            **model_properties(
                Homework,
                ["due_date", "description", "instructions_url"],
            ),
            "state": ref("HomeworkState"),
            **model_properties(
                Homework,
                [
                    "learning_in_public_cap",
                    "homework_url_field",
                    "time_spent_lectures_field",
                    "time_spent_homework_field",
                    "faq_contribution_field",
                ],
            ),
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
            "errors": array_of(JSON),
        },
    },
    "HomeworkPatch": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            **model_properties(
                Homework,
                [
                    "title",
                    "description",
                    "instructions_url",
                    "due_date",
                ],
            ),
            "state": ref("HomeworkState"),
            **model_properties(
                Homework,
                [
                    "learning_in_public_cap",
                    "homework_url_field",
                    "time_spent_lectures_field",
                    "time_spent_homework_field",
                    "faq_contribution_field",
                ],
            ),
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
            "state": ref("HomeworkState"),
            "submissions_count": {"type": "integer"},
            "rescored_submissions_count": {"type": "integer"},
        },
    }
}
