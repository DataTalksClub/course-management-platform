from courses.models.homework import Homework

from ..primitives import (
    JSON,
    array_of,
    model_object_schema,
    model_properties,
    ref,
)


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
        "properties": {"homeworks": array_of(ref("Homework"))},
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
            "questions": array_of(ref("QuestionCreateInline")),
        },
    },
    "HomeworkCreateRequest": {
        "oneOf": [
            ref("HomeworkCreate"),
            array_of(ref("HomeworkCreate")),
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
            "questions": array_of(ref("QuestionCreateInline")),
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
            "created": array_of(ref("Homework")),
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
