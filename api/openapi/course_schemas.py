from courses.models.course import (
    Course,
    CourseRegistration,
    RegistrationCampaign,
)

from .primitives import (
    JSON,
    array_of,
    model_object_schema,
    model_properties,
    ref,
)

COURSE_SUMMARY_REF = ref("CourseSummary")
COURSES_ARRAY = array_of(COURSE_SUMMARY_REF)
HOMEWORK_SUMMARY_REF = ref("HomeworkSummary")
HOMEWORK_SUMMARY_ARRAY = array_of(HOMEWORK_SUMMARY_REF)
PROJECT_SUMMARY_REF = ref("ProjectSummary")
PROJECT_SUMMARY_ARRAY = array_of(PROJECT_SUMMARY_REF)
REGISTRATION_CAMPAIGN_REF = ref("RegistrationCampaign")
REGISTRATION_CAMPAIGN_ARRAY = array_of(REGISTRATION_CAMPAIGN_REF)
REGISTRATION_COUNT_REF = ref("RegistrationCount")
REGISTRATION_COUNT_ARRAY = array_of(REGISTRATION_COUNT_REF)
REGISTRATION_STATS_REF = ref("RegistrationStats")
COURSE_REGISTRATION_REF = ref("CourseRegistration")
COURSE_REGISTRATION_ARRAY = array_of(COURSE_REGISTRATION_REF)

COURSE_SUMMARY_SCHEMA = model_object_schema(
    Course,
    [
        "slug",
        "title",
        "description",
        "start_date",
        "end_date",
        "registration_url",
        "github_repo_url",
        "finished",
        "visible",
    ],
    required_fields=["slug", "title", "description", "finished"],
)
COURSE_CREATE_SCHEMA = model_object_schema(
    Course,
    [
        "slug",
        "title",
        "description",
        "start_date",
        "end_date",
        "registration_url",
        "github_repo_url",
        "social_media_hashtag",
        "faq_document_url",
        "min_projects_to_pass",
        "homework_problems_comments_field",
        "project_passing_score",
        "finished",
        "visible",
    ],
    required_fields=["slug", "title"],
)
COURSE_PATCH_PROPERTIES = model_properties(
    Course,
    [
        "title",
        "description",
        "start_date",
        "end_date",
        "registration_url",
        "github_repo_url",
        "social_media_hashtag",
        "faq_document_url",
        "min_projects_to_pass",
        "homework_problems_comments_field",
        "project_passing_score",
        "finished",
        "visible",
    ],
)
COURSE_DETAIL_EXTRA_PROPERTIES = {
    "homeworks": HOMEWORK_SUMMARY_ARRAY,
    "projects": PROJECT_SUMMARY_ARRAY,
}
COURSE_DETAIL_SCHEMA = model_object_schema(
    Course,
    [
        "slug",
        "title",
        "description",
        "start_date",
        "end_date",
        "registration_url",
        "github_repo_url",
        "finished",
        "visible",
        "social_media_hashtag",
        "faq_document_url",
        "min_projects_to_pass",
        "homework_problems_comments_field",
        "project_passing_score",
    ],
    extra_properties=COURSE_DETAIL_EXTRA_PROPERTIES,
)
REGISTRATION_CAMPAIGN_BASE_PROPERTIES = model_properties(
    RegistrationCampaign,
    [
        "slug",
        "title",
        "edition_label",
        "is_active",
        "marketing_markdown",
        "meta_description",
        "hero_image_url",
        "video_url",
    ],
)
REGISTRATION_CAMPAIGN_CURRENT_COURSE_SCHEMA = {
    "type": ["string", "null"],
    "description": "Slug of the currently promoted course.",
}
REGISTRATION_CAMPAIGN_CURRENT_COURSE_INPUT_SCHEMA = {
    "type": ["string", "null"],
}
REGISTRATION_CAMPAIGN_PROPERTIES = {
    **REGISTRATION_CAMPAIGN_BASE_PROPERTIES,
    "current_course": REGISTRATION_CAMPAIGN_CURRENT_COURSE_SCHEMA,
}
REGISTRATION_CAMPAIGN_INPUT_PROPERTIES = {
    **REGISTRATION_CAMPAIGN_BASE_PROPERTIES,
    "current_course": REGISTRATION_CAMPAIGN_CURRENT_COURSE_INPUT_SCHEMA,
}
COURSE_REGISTRATION_EXTRA_PROPERTIES = {
    "campaign": {"type": "string"},
    "course": {"type": ["string", "null"]},
    "role_display": {"type": "string"},
}
COURSE_REGISTRATION_SCHEMA = model_object_schema(
    CourseRegistration,
    [
        "id",
        "email",
        "name",
        "country",
        "region",
        "role",
        "comment",
        "created_at",
    ],
    extra_properties=COURSE_REGISTRATION_EXTRA_PROPERTIES,
)

COURSE_SCHEMAS = {
    "Error": {
        "type": "object",
        "required": ["error"],
        "properties": {
            "error": {"type": "string"},
            "code": {"type": "string"},
            "details": JSON,
        },
    },
    "Deleted": {
        "type": "object",
        "required": ["deleted"],
        "properties": {"deleted": {"type": "boolean"}},
    },
    "Health": {
        "type": "object",
        "required": ["status", "version"],
        "properties": {
            "status": {"type": "string"},
            "version": {"type": "string"},
        },
    },
    "CourseSummary": COURSE_SUMMARY_SCHEMA,
    "CoursesList": {
        "type": "object",
        "required": ["courses"],
        "properties": {"courses": COURSES_ARRAY},
    },
    "CourseCreate": COURSE_CREATE_SCHEMA,
    "CoursePatch": {
        "type": "object",
        "additionalProperties": False,
        "properties": COURSE_PATCH_PROPERTIES,
    },
    "CourseDetail": COURSE_DETAIL_SCHEMA,
    "RegistrationCampaign": {
        "type": "object",
        "properties": REGISTRATION_CAMPAIGN_PROPERTIES,
    },
    "RegistrationCampaignCreate": {
        "type": "object",
        "required": ["slug", "title"],
        "additionalProperties": False,
        "properties": REGISTRATION_CAMPAIGN_INPUT_PROPERTIES,
    },
    "RegistrationCampaignPatch": {
        "type": "object",
        "additionalProperties": False,
        "properties": REGISTRATION_CAMPAIGN_INPUT_PROPERTIES,
    },
    "RegistrationCampaignsList": {
        "type": "object",
        "required": ["registration_campaigns"],
        "properties": {
            "registration_campaigns": REGISTRATION_CAMPAIGN_ARRAY,
        },
    },
    "CourseRegistration": COURSE_REGISTRATION_SCHEMA,
    "RegistrationCount": {
        "type": "object",
        "properties": {
            "value": {"type": "string"},
            "count": {"type": "integer"},
        },
    },
    "RegistrationStats": {
        "type": "object",
        "properties": {
            "total": {"type": "integer"},
            "by_role": REGISTRATION_COUNT_ARRAY,
            "by_country": REGISTRATION_COUNT_ARRAY,
            "by_region": REGISTRATION_COUNT_ARRAY,
        },
    },
    "RegistrationCampaignRegistrations": {
        "type": "object",
        "properties": {
            "campaign": REGISTRATION_CAMPAIGN_REF,
            "stats": REGISTRATION_STATS_REF,
            "registrations": COURSE_REGISTRATION_ARRAY,
        },
    },
}
