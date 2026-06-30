from courses.models import (
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
    "CourseSummary": model_object_schema(
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
    ),
    "CoursesList": {
        "type": "object",
        "required": ["courses"],
        "properties": {"courses": array_of(ref("CourseSummary"))},
    },
    "CourseCreate": model_object_schema(
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
    ),
    "CoursePatch": {
        "type": "object",
        "additionalProperties": False,
        "properties": model_properties(
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
        ),
    },
    "CourseDetail": model_object_schema(
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
        extra_properties={
            "homeworks": array_of(ref("HomeworkSummary")),
            "projects": array_of(ref("ProjectSummary")),
        },
    ),
    "RegistrationCampaign": {
        "type": "object",
        "properties": {
            **model_properties(
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
            ),
            "current_course": {
                "type": ["string", "null"],
                "description": "Slug of the currently promoted course.",
            },
        },
    },
    "RegistrationCampaignCreate": {
        "type": "object",
        "required": ["slug", "title"],
        "additionalProperties": False,
        "properties": {
            **model_properties(
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
            ),
            "current_course": {"type": ["string", "null"]},
        },
    },
    "RegistrationCampaignPatch": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            **model_properties(
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
            ),
            "current_course": {"type": ["string", "null"]},
        },
    },
    "RegistrationCampaignsList": {
        "type": "object",
        "required": ["registration_campaigns"],
        "properties": {
            "registration_campaigns": array_of(
                ref("RegistrationCampaign")
            ),
        },
    },
    "CourseRegistration": model_object_schema(
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
        extra_properties={
            "campaign": {"type": "string"},
            "course": {"type": ["string", "null"]},
            "role_display": {"type": "string"},
        },
    ),
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
            "by_role": array_of(ref("RegistrationCount")),
            "by_country": array_of(ref("RegistrationCount")),
            "by_region": array_of(ref("RegistrationCount")),
        },
    },
    "RegistrationCampaignRegistrations": {
        "type": "object",
        "properties": {
            "campaign": ref("RegistrationCampaign"),
            "stats": ref("RegistrationStats"),
            "registrations": array_of(ref("CourseRegistration")),
        },
    },
}
