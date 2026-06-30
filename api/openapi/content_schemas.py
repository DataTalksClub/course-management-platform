from courses.models import Homework, Project, Question
from courses.models.homework import AnswerTypes, HomeworkState
from courses.models.project import ProjectState

from .primitives import (
    JSON,
    array_of,
    choices_schema,
    enum_schema,
    model_object_schema,
    model_properties,
    ref,
)

CONTENT_SCHEMAS = {
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
    },
    "ProjectSummary": model_object_schema(
        Project,
        [
            "id",
            "slug",
            "title",
            "instructions_url",
            "submission_due_date",
            "peer_review_due_date",
            "state",
        ],
    ),
    "Project": {
        "allOf": [
            ref("ProjectSummary"),
            {
                "type": "object",
                "properties": {
                    **model_properties(
                        Project,
                        [
                            "description",
                            "instructions_url",
                            "learning_in_public_cap_project",
                            "learning_in_public_cap_review",
                            "number_of_peers_to_evaluate",
                            "points_for_peer_review",
                            "time_spent_project_field",
                            "problems_comments_field",
                            "faq_contribution_field",
                        ],
                    ),
                    "submissions_count": {"type": "integer"},
                    "can_delete": {"type": "boolean"},
                    "delete_blockers": array_of({"type": "string"}),
                },
            },
        ],
    },
    "ProjectsList": {
        "type": "object",
        "required": ["projects"],
        "properties": {"projects": array_of(ref("Project"))},
    },
    "ProjectCreate": {
        "type": "object",
        "required": [
            "name",
            "submission_due_date",
            "peer_review_due_date",
        ],
        "properties": {
            "name": {"type": "string"},
            "slug": {"type": "string"},
            **model_properties(
                Project,
                [
                    "submission_due_date",
                    "peer_review_due_date",
                    "description",
                    "instructions_url",
                ],
            ),
        },
    },
    "ProjectCreateRequest": {
        "oneOf": [ref("ProjectCreate"), array_of(ref("ProjectCreate"))],
    },
    "ProjectUpsert": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "title": {"type": "string"},
            **model_properties(
                Project,
                [
                    "submission_due_date",
                    "peer_review_due_date",
                    "description",
                    "instructions_url",
                ],
            ),
            "state": ref("ProjectState"),
            **model_properties(
                Project,
                [
                    "learning_in_public_cap_project",
                    "learning_in_public_cap_review",
                    "number_of_peers_to_evaluate",
                    "points_for_peer_review",
                    "time_spent_project_field",
                    "problems_comments_field",
                    "faq_contribution_field",
                ],
            ),
        },
        "description": (
            "Idempotent project payload. Creating requires name/title, "
            "submission_due_date, and peer_review_due_date."
        ),
    },
    "ProjectCreateResponse": {
        "type": "object",
        "required": ["created"],
        "properties": {
            "created": array_of(ref("Project")),
            "errors": array_of(JSON),
        },
    },
    "ProjectPatch": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            **model_properties(
                Project,
                [
                    "title",
                    "description",
                    "instructions_url",
                    "submission_due_date",
                    "peer_review_due_date",
                ],
            ),
            "state": ref("ProjectState"),
            **model_properties(
                Project,
                [
                    "learning_in_public_cap_project",
                    "learning_in_public_cap_review",
                    "number_of_peers_to_evaluate",
                    "points_for_peer_review",
                    "time_spent_project_field",
                    "problems_comments_field",
                    "faq_contribution_field",
                ],
            ),
        },
    },
    "ProjectAssignReviewsResponse": {
        "type": "object",
        "required": [
            "status",
            "message",
            "project_id",
            "project_slug",
            "state",
            "peer_reviews_count",
            "assigned_peer_reviews_count",
        ],
        "properties": {
            "status": {"type": "string", "enum": ["OK", "FAIL"]},
            "message": {"type": "string"},
            "project_id": {"type": "integer"},
            "project_slug": {"type": "string"},
            "state": ref("ProjectState"),
            "peer_reviews_count": {"type": "integer"},
            "assigned_peer_reviews_count": {"type": "integer"},
        },
    },
    "ProjectScoreResponse": {
        "type": "object",
        "required": [
            "status",
            "message",
            "project_id",
            "project_slug",
            "state",
            "submissions_count",
            "scored_submissions_count",
            "passed_submissions_count",
        ],
        "properties": {
            "status": {"type": "string", "enum": ["OK", "FAIL"]},
            "message": {"type": "string"},
            "project_id": {"type": "integer"},
            "project_slug": {"type": "string"},
            "state": ref("ProjectState"),
            "submissions_count": {"type": "integer"},
            "scored_submissions_count": {"type": "integer"},
            "passed_submissions_count": {"type": "integer"},
        },
    },
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
    },
    "HomeworkState": enum_schema(
        HomeworkState,
        description="CL=closed, OP=open, SC=scored",
    ),
    "ProjectState": enum_schema(
        ProjectState,
        description=(
            "CL=closed, CS=collecting submissions, PR=peer reviewing, "
            "CO=completed"
        ),
    ),
    "QuestionType": choices_schema(Question.QUESTION_TYPES),
    "AnswerType": enum_schema(AnswerTypes, nullable=True),
}
