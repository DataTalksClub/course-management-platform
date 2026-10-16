from courses.models.project import ReviewCriteria

from ..primitives import JSON, array_of, model_properties, ref


REVIEW_CRITERIA_REF = ref("ReviewCriteria")
REVIEW_CRITERIA_ARRAY = array_of(REVIEW_CRITERIA_REF)
REVIEW_CRITERIA_CREATE_REF = ref("ReviewCriteriaCreate")
REVIEW_CRITERIA_CREATE_ARRAY = array_of(REVIEW_CRITERIA_CREATE_REF)
REVIEW_CRITERIA_ID_PROPERTIES = model_properties(ReviewCriteria, ["id"])
REVIEW_CRITERIA_DESCRIPTION_PROPERTIES = model_properties(
    ReviewCriteria, ["description"]
)
REVIEW_CRITERIA_TYPE_REF = ref("ReviewCriteriaType")
STRING_SCHEMA = {"type": "string"}
DELETE_BLOCKERS_ARRAY = array_of(STRING_SCHEMA)
ERROR_ARRAY = array_of(JSON)
OPTION_SCHEMA = {
    "type": "object",
    "required": ["criteria", "score"],
    "properties": {
        "criteria": {"type": "string"},
        "score": {"type": "integer"},
    },
}
OPTIONS_ARRAY = array_of(OPTION_SCHEMA)

REVIEW_CRITERIA_SCHEMAS = {
    "ReviewCriteria": {
        "type": "object",
        "properties": {
            **REVIEW_CRITERIA_ID_PROPERTIES,
            **REVIEW_CRITERIA_DESCRIPTION_PROPERTIES,
            "review_criteria_type": REVIEW_CRITERIA_TYPE_REF,
            "options": OPTIONS_ARRAY,
            "scores_count": {"type": "integer"},
            "can_delete": {"type": "boolean"},
            "delete_blockers": DELETE_BLOCKERS_ARRAY,
        },
    },
    "ReviewCriteriaList": {
        "type": "object",
        "required": ["course_slug", "course_title", "review_criteria"],
        "properties": {
            "course_slug": {"type": "string"},
            "course_title": {"type": "string"},
            "review_criteria": REVIEW_CRITERIA_ARRAY,
        },
    },
    "ReviewCriteriaCreate": {
        "type": "object",
        "required": ["description"],
        "properties": {
            **REVIEW_CRITERIA_DESCRIPTION_PROPERTIES,
            "review_criteria_type": REVIEW_CRITERIA_TYPE_REF,
            "options": OPTIONS_ARRAY,
        },
    },
    "ReviewCriteriaCreateRequest": {
        "oneOf": [
            REVIEW_CRITERIA_CREATE_REF,
            REVIEW_CRITERIA_CREATE_ARRAY,
        ],
    },
    "ReviewCriteriaCreateResponse": {
        "type": "object",
        "required": ["created"],
        "properties": {
            "created": REVIEW_CRITERIA_ARRAY,
            "errors": ERROR_ARRAY,
        },
    },
    "ReviewCriteriaPatch": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            **REVIEW_CRITERIA_DESCRIPTION_PROPERTIES,
            "review_criteria_type": REVIEW_CRITERIA_TYPE_REF,
            "options": OPTIONS_ARRAY,
        },
    },
}
