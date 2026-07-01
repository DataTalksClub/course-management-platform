from courses.models.project import Project

from ..primitives import (
    JSON,
    array_of,
    model_object_schema,
    model_properties,
    ref,
)


PROJECT_REF = ref("Project")
PROJECT_ARRAY = array_of(PROJECT_REF)
PROJECT_CREATE_REF = ref("ProjectCreate")
PROJECT_CREATE_ARRAY = array_of(PROJECT_CREATE_REF)

PROJECT_SCHEMAS = {
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
        "properties": {"projects": PROJECT_ARRAY},
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
        "oneOf": [PROJECT_CREATE_REF, PROJECT_CREATE_ARRAY],
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
            "created": PROJECT_ARRAY,
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
    }
}
