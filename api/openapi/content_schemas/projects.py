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
PROJECT_SUMMARY_REF = ref("ProjectSummary")
PROJECT_CREATE_REF = ref("ProjectCreate")
PROJECT_CREATE_ARRAY = array_of(PROJECT_CREATE_REF)
PROJECT_STATE_REF = ref("ProjectState")
STRING_SCHEMA = {"type": "string"}
DELETE_BLOCKERS_ARRAY = array_of(STRING_SCHEMA)
ERROR_ARRAY = array_of(JSON)
PROJECT_SUMMARY_SCHEMA = model_object_schema(
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
)
PROJECT_DETAIL_MODEL_PROPERTIES = model_properties(
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
)
PROJECT_DETAIL_EXTENSION_SCHEMA = {
    "type": "object",
    "properties": {
        **PROJECT_DETAIL_MODEL_PROPERTIES,
        "submissions_count": {"type": "integer"},
        "can_delete": {"type": "boolean"},
        "delete_blockers": DELETE_BLOCKERS_ARRAY,
    },
}
PROJECT_DETAIL_ALLOF = [
    PROJECT_SUMMARY_REF,
    PROJECT_DETAIL_EXTENSION_SCHEMA,
]
PROJECT_DEADLINE_CONTENT_PROPERTIES = model_properties(
    Project,
    [
        "submission_due_date",
        "peer_review_due_date",
        "description",
        "instructions_url",
    ],
)
PROJECT_OPTION_PROPERTIES = model_properties(
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
)
PROJECT_PATCH_BASE_PROPERTIES = model_properties(
    Project,
    [
        "title",
        "description",
        "instructions_url",
        "submission_due_date",
        "peer_review_due_date",
    ],
)
PROJECT_CREATE_REQUEST_ONE_OF = [
    PROJECT_CREATE_REF,
    PROJECT_CREATE_ARRAY,
]

PROJECT_SCHEMAS = {
    "ProjectSummary": PROJECT_SUMMARY_SCHEMA,
    "Project": {
        "allOf": PROJECT_DETAIL_ALLOF,
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
            **PROJECT_DEADLINE_CONTENT_PROPERTIES,
        },
    },
    "ProjectCreateRequest": {
        "oneOf": PROJECT_CREATE_REQUEST_ONE_OF,
    },
    "ProjectUpsert": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "title": {"type": "string"},
            **PROJECT_DEADLINE_CONTENT_PROPERTIES,
            "state": PROJECT_STATE_REF,
            **PROJECT_OPTION_PROPERTIES,
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
            "errors": ERROR_ARRAY,
        },
    },
    "ProjectPatch": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            **PROJECT_PATCH_BASE_PROPERTIES,
            "state": PROJECT_STATE_REF,
            **PROJECT_OPTION_PROPERTIES,
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
            "state": PROJECT_STATE_REF,
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
            "state": PROJECT_STATE_REF,
            "submissions_count": {"type": "integer"},
            "scored_submissions_count": {"type": "integer"},
            "passed_submissions_count": {"type": "integer"},
        },
    }
}
