from copy import deepcopy

from django.conf import settings
from django.db import models
from django.http import JsonResponse
from django.urls import reverse

from accounts.auth import token_required
from courses.models import (
    Course,
    CourseRegistration,
    Homework,
    Project,
    Question,
    RegistrationCampaign,
)
from courses.models.homework import AnswerTypes, HomeworkState
from courses.models.project import ProjectState


JSON = {"type": "object", "additionalProperties": True}


def ref(name):
    return {"$ref": f"#/components/schemas/{name}"}


def array_of(schema):
    return {"type": "array", "items": schema}


def json_content(schema):
    return {"application/json": {"schema": schema}}


def response(description, schema=None):
    result = {"description": description}
    if schema is not None:
        result["content"] = json_content(schema)
    return result


def content_response(description, content):
    return {
        "description": description,
        "content": content,
    }


def request_body(schema, required=True):
    return {
        "required": required,
        "content": json_content(schema),
    }


def enum_schema(enum_class, *, nullable=False, description=None):
    values = [item.value for item in enum_class]
    schema_type = "string"
    if nullable:
        values.append(None)
        schema_type = ["string", "null"]

    schema = {
        "type": schema_type,
        "enum": values,
    }
    if description:
        schema["description"] = description
    return schema


def choices_schema(choices, *, nullable=False):
    values = [value for value, _label in choices]
    schema_type = "string"
    if nullable:
        values.append(None)
        schema_type = ["string", "null"]
    return {"type": schema_type, "enum": values}


MODEL_FIELD_SCHEMA_TYPES = (
    (models.BooleanField, {"type": "boolean"}),
    (models.IntegerField, {"type": "integer"}),
    (models.FloatField, {"type": "number"}),
    (models.DateTimeField, {"type": "string", "format": "date-time"}),
    (models.DateField, {"type": "string", "format": "date"}),
    (models.URLField, {"type": "string", "format": "uri"}),
)


def _typed_model_field_schema(field):
    for field_type, schema in MODEL_FIELD_SCHEMA_TYPES:
        if isinstance(field, field_type):
            return dict(schema)

    return {"type": "string"}


def model_field_schema(field):
    if field.choices:
        return choices_schema(field.choices, nullable=field.null)

    schema = _typed_model_field_schema(field)
    if field.null:
        schema["nullable"] = True

    return schema


def model_properties(model, fields):
    return {
        field_name: model_field_schema(
            model._meta.get_field(field_name)
        )
        for field_name in fields
    }


def model_object_schema(
    model, fields, *, required=None, extra_properties=None
):
    properties = model_properties(model, fields)
    if extra_properties:
        properties.update(extra_properties)

    schema = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required
    return schema


def auth_required(operation):
    result = deepcopy(operation)
    result["security"] = [{"TokenAuth": []}]
    result.setdefault("responses", {})["401"] = response(
        "Authentication token missing or invalid",
        ref("Error"),
    )
    return result


def operation(
    url_name,
    tags,
    summary,
    responses,
    *,
    parameters=None,
    body=None,
    requires_auth=None,
    description=None,
):
    result = {
        "tags": tags,
        "summary": summary,
        "operationId": url_name,
        "x-django-url-name": url_name,
        "responses": responses,
    }
    if description:
        result["description"] = description
    if parameters:
        result["parameters"] = parameters
    if body:
        result["requestBody"] = body
    if requires_auth is True:
        result = auth_required(result)
    return result


def documented_urlpatterns():
    from api.urls import urlpatterns as api_urlpatterns

    return api_urlpatterns


def _sample_url_value(name, converter, index):
    if converter.regex == "[0-9]+":
        return 100000 + index
    return f"openapi-{name.replace('_', '-')}"


def _reverse_kwargs(pattern):
    return {
        name: _sample_url_value(name, converter, index)
        for index, (name, converter) in enumerate(
            pattern.pattern.converters.items(),
            start=1,
        )
    }


def openapi_path_for_url_name(url_name):
    pattern = next(
        pattern
        for pattern in documented_urlpatterns()
        if pattern.name == url_name
    )
    kwargs = _reverse_kwargs(pattern)
    path = reverse(url_name, kwargs=kwargs)

    for name, value in kwargs.items():
        path = path.replace(str(value), f"{{{name}}}", 1)

    return path


def pattern_for_url_name(url_name):
    return next(
        pattern
        for pattern in documented_urlpatterns()
        if pattern.name == url_name
    )


def view_for_url_name(url_name):
    return pattern_for_url_name(url_name).callback


def parameter_schema_for_converter(converter):
    if converter.regex == "[0-9]+":
        return {"type": "integer"}
    return {"type": "string"}


def path_parameters_for_url_name(url_name):
    pattern = pattern_for_url_name(url_name)
    return [
        {
            "name": name,
            "in": "path",
            "required": True,
            "schema": parameter_schema_for_converter(converter),
        }
        for name, converter in pattern.pattern.converters.items()
    ]


def apply_inspected_operation_metadata(url_name, operation):
    result = deepcopy(operation)

    generated_parameters = path_parameters_for_url_name(url_name)
    explicit_parameters = [
        parameter
        for parameter in result.get("parameters", [])
        if parameter.get("in") != "path"
    ]
    if generated_parameters or explicit_parameters:
        result["parameters"] = [
            *generated_parameters,
            *explicit_parameters,
        ]

    view = view_for_url_name(url_name)
    if getattr(view, "requires_token_auth", False):
        result = auth_required(result)

    return result


def routed_paths():
    return {
        openapi_path_for_url_name(pattern.name)
        for pattern in documented_urlpatterns()
        if pattern.name != "api_openapi_json"
    }


def routed_url_names():
    return {
        pattern.name
        for pattern in documented_urlpatterns()
        if pattern.name != "api_openapi_json"
    }


def route_coverage(paths):
    documented = set(paths)
    routed = routed_paths()

    return {
        "routed_count": len(routed),
        "documented_count": len(documented),
        "undocumented": sorted(routed - documented),
        "documented_without_route": sorted(documented - routed),
    }


def build_openapi_paths():
    return {
        openapi_path_for_url_name(url_name): {
            method: apply_inspected_operation_metadata(
                url_name, operation
            )
            for method, operation in methods.items()
        }
        for url_name, methods in PATHS_BY_URL_NAME.items()
    }


SCHEMAS = {
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
        required=["slug", "title", "description", "finished"],
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
        required=["slug", "title"],
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
    "Graduates": {
        "type": "object",
        "required": ["graduates"],
        "properties": {
            "graduates": array_of(
                {
                    "type": "object",
                    "required": ["email", "name"],
                    "properties": {
                        "email": {"type": "string"},
                        "name": {"type": "string"},
                    },
                }
            )
        },
    },
    "CertificateUpdate": {
        "type": "object",
        "required": ["email", "certificate_path"],
        "properties": {
            "email": {"type": "string"},
            "certificate_path": {"type": "string"},
        },
    },
    "CertificateUpdateRequest": {
        "oneOf": [
            {
                "type": "object",
                "required": ["certificates"],
                "properties": {
                    "certificates": array_of(ref("CertificateUpdate")),
                },
            },
            array_of(ref("CertificateUpdate")),
        ],
    },
    "CertificateUpdateResult": {
        "type": "object",
        "properties": {
            "index": {"type": "integer"},
            "email": {"type": "string"},
            "enrollment_id": {"type": "integer"},
            "certificate_url": {"type": "string"},
        },
    },
    "CertificateUpdateError": {
        "type": "object",
        "properties": {
            "index": {"type": "integer"},
            "email": {"type": "string"},
            "code": {"type": "string"},
            "error": {"type": "string"},
        },
    },
    "CertificateUpdateResponse": {
        "type": "object",
        "required": ["success", "updated_count", "error_count"],
        "properties": {
            "success": {"type": "boolean"},
            "updated_count": {"type": "integer"},
            "error_count": {"type": "integer"},
            "updated": array_of(ref("CertificateUpdateResult")),
            "errors": array_of(ref("CertificateUpdateError")),
        },
    },
    "DatamailerEvent": {
        "type": "object",
        "required": ["event_id", "event_type", "email"],
        "properties": {
            "event_id": {"type": "string"},
            "event_type": {
                "type": "string",
                "enum": [
                    "contact.hard_bounced",
                    "contact.complained",
                    "subscription.unsubscribed",
                    "subscription.resubscribed",
                    "message.delivered",
                    "message.opened",
                    "message.clicked",
                    "transactional.skipped",
                    "transactional.failed",
                ],
            },
            "email": {"type": "string", "format": "email"},
            "occurred_at": {"type": "string", "format": "date-time"},
            "audience": {"type": "string"},
            "client": {"type": "string"},
            "preference_key": {
                "type": "string",
                "enum": [
                    "email_submission_confirmations",
                    "email_deadline_reminders",
                    "email_course_updates",
                ],
            },
            "metadata": JSON,
        },
        "additionalProperties": True,
    },
    "DatamailerEventAccepted": {
        "type": "object",
        "required": ["ok", "created", "preference_updated"],
        "properties": {
            "ok": {"type": "boolean"},
            "created": {"type": "boolean"},
            "preference_updated": {"type": "boolean"},
        },
    },
}


PATHS_BY_URL_NAME = {
    "api_health": {
        "get": operation(
            "api_health",
            ["System"],
            "Health check",
            {"200": response("Service status", ref("Health"))},
            requires_auth=False,
        ),
    },
    "api_course_criteria_yaml": {
        "get": operation(
            "api_course_criteria_yaml",
            ["Course Data"],
            "Get course criteria YAML",
            {
                "200": content_response(
                    "Course criteria YAML",
                    {"text/yaml": {"schema": {"type": "string"}}},
                ),
                "404": response("Course not found", ref("Error")),
            },
            requires_auth=False,
        ),
    },
    "api_course_leaderboard": {
        "get": operation(
            "api_course_leaderboard",
            ["Course Data"],
            "Get leaderboard YAML",
            {
                "200": content_response(
                    "Leaderboard YAML",
                    {"text/plain": {"schema": {"type": "string"}}},
                ),
                "404": response("Course not found", ref("Error")),
            },
            requires_auth=False,
        ),
    },
    "api_homework_submissions_export": {
        "get": operation(
            "api_homework_submissions_export",
            ["Course Data"],
            "Export homework submissions",
            {
                "200": response("Homework submissions export", JSON),
                "404": response(
                    "Course or homework not found", ref("Error")
                ),
            },
        ),
    },
    "api_project_submissions_export": {
        "get": operation(
            "api_project_submissions_export",
            ["Course Data"],
            "Export project submissions",
            {
                "200": response("Project submissions export", JSON),
                "404": response(
                    "Course or project not found", ref("Error")
                ),
            },
        ),
    },
    "api_course_graduates": {
        "get": operation(
            "api_course_graduates",
            ["Course Data"],
            "Get course graduates",
            {
                "200": response("Course graduates", ref("Graduates")),
                "404": response("Course not found", ref("Error")),
            },
        ),
    },
    "api_course_certificates": {
        "post": operation(
            "api_course_certificates",
            ["Course Data"],
            "Bulk update enrollment certificate URLs",
            {
                "200": response(
                    "Certificate update result",
                    ref("CertificateUpdateResponse"),
                ),
                "400": response("Invalid request", ref("Error")),
                "404": response("Course not found", ref("Error")),
            },
            body=request_body(ref("CertificateUpdateRequest")),
            description=(
                "Updates many enrollment certificate URLs in one request. "
                "The response includes per-entry errors for missing users, "
                "unenrolled users, and invalid entries."
            ),
        ),
    },
    "api_datamailer_events": {
        "post": operation(
            "api_datamailer_events",
            ["Datamailer"],
            "Receive Datamailer contact event",
            {
                "200": response(
                    "Datamailer event accepted",
                    ref("DatamailerEventAccepted"),
                ),
                "400": response("Invalid event payload", ref("Error")),
                "401": response("Invalid webhook token", ref("Error")),
                "503": response("Webhook not configured", ref("Error")),
            },
            body=request_body(ref("DatamailerEvent")),
            requires_auth=False,
            description=(
                "Webhook used by Datamailer to report hard bounces, "
                "complaints, subscription changes, skipped/failed sends, and "
                "message lifecycle events back to CMP for support and audit "
                "visibility. CMP records these callbacks but does not use them "
                "as its email preference store. The request must include the "
                "configured Datamailer webhook token in the Authorization "
                "bearer token or X-Datamailer-Webhook-Token header."
            ),
        ),
    },
    "api_courses_list": {
        "get": operation(
            "api_courses_list",
            ["Courses"],
            "List courses",
            {"200": response("Course list", ref("CoursesList"))},
        ),
        "post": operation(
            "api_courses_list",
            ["Courses"],
            "Create course",
            {
                "201": response("Created course", ref("CourseDetail")),
                "400": response("Invalid request", ref("Error")),
            },
            body=request_body(ref("CourseCreate")),
        ),
    },
    "api_course_detail": {
        "get": operation(
            "api_course_detail",
            ["Courses"],
            "Get course details",
            {
                "200": response("Course details", ref("CourseDetail")),
                "404": response("Course not found", ref("Error")),
            },
        ),
        "patch": operation(
            "api_course_detail",
            ["Courses"],
            "Update course",
            {
                "200": response("Updated course", ref("CourseDetail")),
                "400": response("Invalid field", ref("Error")),
                "404": response("Course not found", ref("Error")),
            },
            body=request_body(ref("CoursePatch")),
        ),
    },
    "api_registration_campaigns": {
        "get": operation(
            "api_registration_campaigns",
            ["Registration Campaigns"],
            "List registration campaigns",
            {
                "200": response(
                    "Registration campaign list",
                    ref("RegistrationCampaignsList"),
                ),
            },
        ),
        "post": operation(
            "api_registration_campaigns",
            ["Registration Campaigns"],
            "Create registration campaign",
            {
                "201": response(
                    "Created registration campaign",
                    ref("RegistrationCampaign"),
                ),
                "400": response("Invalid request", ref("Error")),
            },
            body=request_body(ref("RegistrationCampaignCreate")),
        ),
    },
    "api_registration_campaign_detail": {
        "get": operation(
            "api_registration_campaign_detail",
            ["Registration Campaigns"],
            "Get registration campaign",
            {
                "200": response(
                    "Registration campaign",
                    ref("RegistrationCampaign"),
                ),
                "404": response(
                    "Registration campaign not found", ref("Error")
                ),
            },
        ),
        "patch": operation(
            "api_registration_campaign_detail",
            ["Registration Campaigns"],
            "Update registration campaign",
            {
                "200": response(
                    "Updated registration campaign",
                    ref("RegistrationCampaign"),
                ),
                "400": response("Invalid request", ref("Error")),
                "404": response(
                    "Registration campaign not found", ref("Error")
                ),
            },
            body=request_body(ref("RegistrationCampaignPatch")),
        ),
    },
    "api_registration_campaign_registrations": {
        "get": operation(
            "api_registration_campaign_registrations",
            ["Registration Campaigns"],
            "List registration campaign registrations and stats",
            {
                "200": response(
                    "Registration campaign registrations",
                    ref("RegistrationCampaignRegistrations"),
                ),
                "404": response(
                    "Registration campaign not found", ref("Error")
                ),
            },
        ),
    },
    "api_homeworks": {
        "get": operation(
            "api_homeworks",
            ["Homeworks"],
            "List homeworks",
            {"200": response("Homework list", ref("HomeworksList"))},
        ),
        "post": operation(
            "api_homeworks",
            ["Homeworks"],
            "Create homework or homeworks",
            {
                "201": response(
                    "Created homeworks", ref("HomeworkCreateResponse")
                ),
                "400": response("Invalid request", ref("Error")),
                "404": response("Course not found", ref("Error")),
            },
            body=request_body(ref("HomeworkCreateRequest")),
        ),
    },
    "api_homework_detail": {
        "get": operation(
            "api_homework_detail",
            ["Homeworks"],
            "Get homework details",
            {
                "200": response("Homework details", ref("Homework")),
                "404": response(
                    "Course or homework not found", ref("Error")
                ),
            },
        ),
        "patch": operation(
            "api_homework_detail",
            ["Homeworks"],
            "Update homework",
            {
                "200": response("Updated homework", ref("Homework")),
                "400": response(
                    "Invalid field, state, or date", ref("Error")
                ),
                "404": response(
                    "Course or homework not found", ref("Error")
                ),
            },
            body=request_body(ref("HomeworkPatch")),
        ),
        "delete": operation(
            "api_homework_detail",
            ["Homeworks"],
            "Delete homework",
            {
                "200": response("Deleted", ref("Deleted")),
                "400": response(
                    "Homework is not closed or has submissions",
                    ref("Error"),
                ),
                "404": response(
                    "Course or homework not found", ref("Error")
                ),
            },
            description=(
                "Deletes a homework only when state is CL and there are no "
                "submissions. This endpoint never deletes submission data."
            ),
        ),
    },
    "api_homework_score": {
        "post": operation(
            "api_homework_score",
            ["Homeworks"],
            "Score homework submissions",
            {
                "200": response(
                    "Homework scored", ref("HomeworkScoreResponse")
                ),
                "400": response(
                    "Scoring blocked", ref("HomeworkScoreResponse")
                ),
                "403": response("Staff token required", ref("Error")),
                "404": response(
                    "Course or homework not found", ref("Error")
                ),
            },
            description=(
                "Scores homework submissions with the same safeguards as "
                "cadmin: due date must be in the past, state must be OP, "
                "and already scored homeworks are rejected."
            ),
        ),
    },
    "api_homework_detail_by_slug": {
        "get": operation(
            "api_homework_detail_by_slug",
            ["Homeworks"],
            "Get homework details by slug",
            {
                "200": response("Homework details", ref("Homework")),
                "404": response(
                    "Course or homework not found", ref("Error")
                ),
            },
        ),
        "patch": operation(
            "api_homework_detail_by_slug",
            ["Homeworks"],
            "Update homework by slug",
            {
                "200": response("Updated homework", ref("Homework")),
                "400": response(
                    "Invalid field, state, or date", ref("Error")
                ),
                "404": response(
                    "Course or homework not found", ref("Error")
                ),
            },
            body=request_body(ref("HomeworkPatch")),
        ),
        "put": operation(
            "api_homework_detail_by_slug",
            ["Homeworks"],
            "Create or update homework by slug",
            {
                "200": response("Updated homework", ref("Homework")),
                "201": response("Created homework", ref("Homework")),
                "400": response(
                    "Invalid request or replace blocked", ref("Error")
                ),
                "404": response("Course not found", ref("Error")),
            },
            body=request_body(ref("HomeworkUpsert")),
            description=(
                "Idempotently creates or updates a homework using the slug in "
                "the path. If questions are supplied for an existing homework, "
                "they replace current questions only when the homework is "
                "closed and has no submissions."
            ),
        ),
        "delete": operation(
            "api_homework_detail_by_slug",
            ["Homeworks"],
            "Delete homework by slug",
            {
                "200": response("Deleted", ref("Deleted")),
                "400": response(
                    "Homework is not closed or has submissions",
                    ref("Error"),
                ),
                "404": response(
                    "Course or homework not found", ref("Error")
                ),
            },
            description=(
                "Deletes a homework only when state is CL and there are no "
                "submissions. This endpoint never deletes submission data."
            ),
        ),
    },
    "api_homework_score_by_slug": {
        "post": operation(
            "api_homework_score_by_slug",
            ["Homeworks"],
            "Score homework submissions by slug",
            {
                "200": response(
                    "Homework scored", ref("HomeworkScoreResponse")
                ),
                "400": response(
                    "Scoring blocked", ref("HomeworkScoreResponse")
                ),
                "403": response("Staff token required", ref("Error")),
                "404": response(
                    "Course or homework not found", ref("Error")
                ),
            },
            description=(
                "Scores homework submissions with the same safeguards as "
                "cadmin: due date must be in the past, state must be OP, "
                "and already scored homeworks are rejected."
            ),
        ),
    },
    "api_projects": {
        "get": operation(
            "api_projects",
            ["Projects"],
            "List projects",
            {"200": response("Project list", ref("ProjectsList"))},
        ),
        "post": operation(
            "api_projects",
            ["Projects"],
            "Create project or projects",
            {
                "201": response(
                    "Created projects", ref("ProjectCreateResponse")
                ),
                "400": response("Invalid request", ref("Error")),
                "404": response("Course not found", ref("Error")),
            },
            body=request_body(ref("ProjectCreateRequest")),
        ),
    },
    "api_project_detail": {
        "get": operation(
            "api_project_detail",
            ["Projects"],
            "Get project details",
            {
                "200": response("Project details", ref("Project")),
                "404": response(
                    "Course or project not found", ref("Error")
                ),
            },
        ),
        "patch": operation(
            "api_project_detail",
            ["Projects"],
            "Update project",
            {
                "200": response("Updated project", ref("Project")),
                "400": response(
                    "Invalid field, state, or date", ref("Error")
                ),
                "404": response(
                    "Course or project not found", ref("Error")
                ),
            },
            body=request_body(ref("ProjectPatch")),
        ),
        "delete": operation(
            "api_project_detail",
            ["Projects"],
            "Delete project",
            {
                "200": response("Deleted", ref("Deleted")),
                "400": response(
                    "Project is not closed or has submissions",
                    ref("Error"),
                ),
                "404": response(
                    "Course or project not found", ref("Error")
                ),
            },
            description=(
                "Deletes a project only when state is CL and there are no "
                "submissions. This endpoint never deletes submission data."
            ),
        ),
    },
    "api_project_assign_reviews": {
        "post": operation(
            "api_project_assign_reviews",
            ["Projects"],
            "Assign project peer reviews",
            {
                "200": response(
                    "Peer reviews assigned",
                    ref("ProjectAssignReviewsResponse"),
                ),
                "400": response(
                    "Assignment blocked",
                    ref("ProjectAssignReviewsResponse"),
                ),
                "403": response("Staff token required", ref("Error")),
                "404": response(
                    "Course or project not found", ref("Error")
                ),
            },
            description=(
                "Assigns peer reviews with the same safeguards as cadmin: "
                "project state must be CS, submission due date must be in "
                "the past, and enough submissions must exist."
            ),
        ),
    },
    "api_project_score": {
        "post": operation(
            "api_project_score",
            ["Projects"],
            "Score project",
            {
                "200": response(
                    "Project scored", ref("ProjectScoreResponse")
                ),
                "400": response(
                    "Scoring blocked", ref("ProjectScoreResponse")
                ),
                "403": response("Staff token required", ref("Error")),
                "404": response(
                    "Course or project not found", ref("Error")
                ),
            },
            description=(
                "Scores project submissions with the same safeguards as "
                "cadmin: project state must be PR, peer review due date "
                "must be in the past, and peer reviews must exist."
            ),
        ),
    },
    "api_project_detail_by_slug": {
        "get": operation(
            "api_project_detail_by_slug",
            ["Projects"],
            "Get project details by slug",
            {
                "200": response("Project details", ref("Project")),
                "404": response(
                    "Course or project not found", ref("Error")
                ),
            },
        ),
        "patch": operation(
            "api_project_detail_by_slug",
            ["Projects"],
            "Update project by slug",
            {
                "200": response("Updated project", ref("Project")),
                "400": response(
                    "Invalid field, state, or date", ref("Error")
                ),
                "404": response(
                    "Course or project not found", ref("Error")
                ),
            },
            body=request_body(ref("ProjectPatch")),
        ),
        "put": operation(
            "api_project_detail_by_slug",
            ["Projects"],
            "Create or update project by slug",
            {
                "200": response("Updated project", ref("Project")),
                "201": response("Created project", ref("Project")),
                "400": response("Invalid request", ref("Error")),
                "404": response("Course not found", ref("Error")),
            },
            body=request_body(ref("ProjectUpsert")),
            description=(
                "Idempotently creates or updates a project using the slug in "
                "the path."
            ),
        ),
        "delete": operation(
            "api_project_detail_by_slug",
            ["Projects"],
            "Delete project by slug",
            {
                "200": response("Deleted", ref("Deleted")),
                "400": response(
                    "Project is not closed or has submissions",
                    ref("Error"),
                ),
                "404": response(
                    "Course or project not found", ref("Error")
                ),
            },
            description=(
                "Deletes a project only when state is CL and there are no "
                "submissions. This endpoint never deletes submission data."
            ),
        ),
    },
    "api_project_assign_reviews_by_slug": {
        "post": operation(
            "api_project_assign_reviews_by_slug",
            ["Projects"],
            "Assign project peer reviews by slug",
            {
                "200": response(
                    "Peer reviews assigned",
                    ref("ProjectAssignReviewsResponse"),
                ),
                "400": response(
                    "Assignment blocked",
                    ref("ProjectAssignReviewsResponse"),
                ),
                "403": response("Staff token required", ref("Error")),
                "404": response(
                    "Course or project not found", ref("Error")
                ),
            },
            description=(
                "Assigns peer reviews with the same safeguards as cadmin: "
                "project state must be CS, submission due date must be in "
                "the past, and enough submissions must exist."
            ),
        ),
    },
    "api_project_score_by_slug": {
        "post": operation(
            "api_project_score_by_slug",
            ["Projects"],
            "Score project by slug",
            {
                "200": response(
                    "Project scored", ref("ProjectScoreResponse")
                ),
                "400": response(
                    "Scoring blocked", ref("ProjectScoreResponse")
                ),
                "403": response("Staff token required", ref("Error")),
                "404": response(
                    "Course or project not found", ref("Error")
                ),
            },
            description=(
                "Scores project submissions with the same safeguards as "
                "cadmin: project state must be PR, peer review due date "
                "must be in the past, and peer reviews must exist."
            ),
        ),
    },
    "api_questions": {
        "get": operation(
            "api_questions",
            ["Questions"],
            "List homework questions",
            {"200": response("Question list", ref("QuestionsList"))},
        ),
        "post": operation(
            "api_questions",
            ["Questions"],
            "Create question or questions",
            {
                "201": response(
                    "Created questions", ref("QuestionCreateResponse")
                ),
                "400": response("Invalid request", ref("Error")),
                "404": response(
                    "Course or homework not found", ref("Error")
                ),
            },
            body=request_body(ref("QuestionCreateRequest")),
        ),
    },
    "api_question_detail": {
        "get": operation(
            "api_question_detail",
            ["Questions"],
            "Get question details",
            {
                "200": response("Question details", ref("Question")),
                "404": response("Question not found", ref("Error")),
            },
        ),
        "patch": operation(
            "api_question_detail",
            ["Questions"],
            "Update question",
            {
                "200": response("Updated question", ref("Question")),
                "400": response("Invalid field", ref("Error")),
                "404": response("Question not found", ref("Error")),
            },
            body=request_body(ref("QuestionPatch")),
        ),
        "delete": operation(
            "api_question_detail",
            ["Questions"],
            "Delete question",
            {
                "200": response("Deleted", ref("Deleted")),
                "400": response("Question has answers", ref("Error")),
                "404": response("Question not found", ref("Error")),
            },
            description=(
                "Deletes a question only when it has no answers. This "
                "endpoint never deletes submitted answer data."
            ),
        ),
    },
}


def build_openapi_spec():
    paths = build_openapi_paths()

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Course Management Platform API",
            "version": settings.VERSION,
            "description": (
                "Generated OpenAPI specification for the course management, "
                "course data export, and operational endpoints. Treat this "
                "document as the source of truth for agent API usage."
            ),
        },
        "paths": paths,
        "x-route-coverage": route_coverage(paths),
        "components": {
            "securitySchemes": {
                "TokenAuth": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "Authorization",
                    "description": "Use `Token <token_key>`.",
                },
            },
            "schemas": deepcopy(SCHEMAS),
        },
    }


@token_required
def openapi_json_view(request):
    return JsonResponse(build_openapi_spec())
