from copy import deepcopy

from django.conf import settings
from django.http import JsonResponse

from accounts.auth import token_required


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


def path_param(name, schema_type="string"):
    return {
        "name": name,
        "in": "path",
        "required": True,
        "schema": {"type": schema_type},
    }


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
    requires_auth=True,
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
    if requires_auth:
        result = auth_required(result)
    return result


COURSE_SLUG = path_param("course_slug")
HOMEWORK_SLUG = path_param("homework_slug")
HOMEWORK_ID = path_param("homework_id", "integer")
PROJECT_SLUG = path_param("project_slug")
PROJECT_ID = path_param("project_id", "integer")
QUESTION_ID = path_param("question_id", "integer")


def route_to_openapi_path(route):
    return (
        "/api/"
        + route.replace("<slug:course_slug>", "{course_slug}")
        .replace("<slug:homework_slug>", "{homework_slug}")
        .replace("<int:homework_id>", "{homework_id}")
        .replace("<slug:project_slug>", "{project_slug}")
        .replace("<int:project_id>", "{project_id}")
        .replace("<int:question_id>", "{question_id}")
    )


def documented_urlpatterns():
    from api.urls import urlpatterns as api_urlpatterns
    from data.urls import urlpatterns as data_urlpatterns

    return [*api_urlpatterns, *data_urlpatterns]


def routed_paths():
    return {
        route_to_openapi_path(pattern.pattern._route)
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
    "CourseSummary": {
        "type": "object",
        "required": ["slug", "title", "description", "finished"],
        "properties": {
            "slug": {"type": "string"},
            "title": {"type": "string"},
            "description": {"type": "string"},
            "finished": {"type": "boolean"},
            "visible": {"type": "boolean"},
        },
    },
    "CoursesList": {
        "type": "object",
        "required": ["courses"],
        "properties": {"courses": array_of(ref("CourseSummary"))},
    },
    "CourseCreate": {
        "type": "object",
        "required": ["slug", "title"],
        "properties": {
            "slug": {"type": "string"},
            "title": {"type": "string"},
            "description": {"type": "string"},
            "social_media_hashtag": {"type": "string"},
            "faq_document_url": {"type": "string"},
            "min_projects_to_pass": {"type": "integer"},
            "homework_problems_comments_field": {"type": "boolean"},
            "project_passing_score": {"type": "integer"},
            "finished": {"type": "boolean"},
            "visible": {"type": "boolean"},
        },
    },
    "CoursePatch": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string"},
            "social_media_hashtag": {"type": "string"},
            "faq_document_url": {"type": "string"},
            "min_projects_to_pass": {"type": "integer"},
            "homework_problems_comments_field": {"type": "boolean"},
            "project_passing_score": {"type": "integer"},
            "finished": {"type": "boolean"},
            "visible": {"type": "boolean"},
        },
    },
    "CourseDetail": {
        "type": "object",
        "properties": {
            "slug": {"type": "string"},
            "title": {"type": "string"},
            "description": {"type": "string"},
            "finished": {"type": "boolean"},
            "visible": {"type": "boolean"},
            "social_media_hashtag": {"type": "string"},
            "faq_document_url": {"type": "string"},
            "min_projects_to_pass": {"type": "integer"},
            "homework_problems_comments_field": {"type": "boolean"},
            "project_passing_score": {"type": "integer"},
            "homeworks": array_of(ref("HomeworkSummary")),
            "projects": array_of(ref("ProjectSummary")),
        },
    },
    "HomeworkSummary": {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "slug": {"type": "string"},
            "title": {"type": "string"},
            "instructions_url": {"type": "string", "format": "uri", "nullable": True},
            "due_date": {"type": "string", "format": "date-time"},
            "state": {"$ref": "#/components/schemas/HomeworkState"},
        },
    },
    "Homework": {
        "allOf": [
            ref("HomeworkSummary"),
            {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "instructions_url": {
                        "type": "string",
                        "format": "uri",
                        "nullable": True,
                    },
                    "learning_in_public_cap": {"type": "integer"},
                    "homework_url_field": {"type": "boolean"},
                    "time_spent_lectures_field": {"type": "boolean"},
                    "time_spent_homework_field": {"type": "boolean"},
                    "faq_contribution_field": {"type": "boolean"},
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
            "due_date": {"type": "string", "format": "date-time"},
            "description": {"type": "string"},
            "instructions_url": {"type": "string", "format": "uri"},
            "questions": array_of(ref("QuestionCreateInline")),
        },
    },
    "HomeworkCreateRequest": {
        "oneOf": [ref("HomeworkCreate"), array_of(ref("HomeworkCreate"))],
    },
    "HomeworkUpsert": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "title": {"type": "string"},
            "due_date": {"type": "string", "format": "date-time"},
            "description": {"type": "string"},
            "instructions_url": {"type": "string", "format": "uri"},
            "state": ref("HomeworkState"),
            "learning_in_public_cap": {"type": "integer"},
            "homework_url_field": {"type": "boolean"},
            "time_spent_lectures_field": {"type": "boolean"},
            "time_spent_homework_field": {"type": "boolean"},
            "faq_contribution_field": {"type": "boolean"},
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
            "title": {"type": "string"},
            "description": {"type": "string"},
            "instructions_url": {"type": "string", "format": "uri"},
            "due_date": {"type": "string", "format": "date-time"},
            "state": ref("HomeworkState"),
            "learning_in_public_cap": {"type": "integer"},
            "homework_url_field": {"type": "boolean"},
            "time_spent_lectures_field": {"type": "boolean"},
            "time_spent_homework_field": {"type": "boolean"},
            "faq_contribution_field": {"type": "boolean"},
        },
    },
    "ProjectSummary": {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "slug": {"type": "string"},
            "title": {"type": "string"},
            "instructions_url": {"type": "string", "format": "uri", "nullable": True},
            "submission_due_date": {"type": "string", "format": "date-time"},
            "peer_review_due_date": {"type": "string", "format": "date-time"},
            "state": {"$ref": "#/components/schemas/ProjectState"},
        },
    },
    "Project": {
        "allOf": [
            ref("ProjectSummary"),
            {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "instructions_url": {
                        "type": "string",
                        "format": "uri",
                        "nullable": True,
                    },
                    "learning_in_public_cap_project": {"type": "integer"},
                    "learning_in_public_cap_review": {"type": "integer"},
                    "number_of_peers_to_evaluate": {"type": "integer"},
                    "points_for_peer_review": {"type": "integer"},
                    "time_spent_project_field": {"type": "boolean"},
                    "problems_comments_field": {"type": "boolean"},
                    "faq_contribution_field": {"type": "boolean"},
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
            "submission_due_date": {
                "type": "string",
                "format": "date-time",
            },
            "peer_review_due_date": {
                "type": "string",
                "format": "date-time",
            },
            "description": {"type": "string"},
            "instructions_url": {"type": "string", "format": "uri"},
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
            "submission_due_date": {
                "type": "string",
                "format": "date-time",
            },
            "peer_review_due_date": {
                "type": "string",
                "format": "date-time",
            },
            "description": {"type": "string"},
            "instructions_url": {"type": "string", "format": "uri"},
            "state": ref("ProjectState"),
            "learning_in_public_cap_project": {"type": "integer"},
            "learning_in_public_cap_review": {"type": "integer"},
            "number_of_peers_to_evaluate": {"type": "integer"},
            "points_for_peer_review": {"type": "integer"},
            "time_spent_project_field": {"type": "boolean"},
            "problems_comments_field": {"type": "boolean"},
            "faq_contribution_field": {"type": "boolean"},
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
            "title": {"type": "string"},
            "description": {"type": "string"},
            "instructions_url": {"type": "string", "format": "uri"},
            "submission_due_date": {
                "type": "string",
                "format": "date-time",
            },
            "peer_review_due_date": {
                "type": "string",
                "format": "date-time",
            },
            "state": ref("ProjectState"),
            "learning_in_public_cap_project": {"type": "integer"},
            "learning_in_public_cap_review": {"type": "integer"},
            "number_of_peers_to_evaluate": {"type": "integer"},
            "points_for_peer_review": {"type": "integer"},
            "time_spent_project_field": {"type": "boolean"},
            "problems_comments_field": {"type": "boolean"},
            "faq_contribution_field": {"type": "boolean"},
        },
    },
    "Question": {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "text": {"type": "string"},
            "question_type": ref("QuestionType"),
            "answer_type": ref("AnswerType"),
            "possible_answers": array_of({"type": "string"}),
            "correct_answer": {"type": "string"},
            "scores_for_correct_answer": {"type": "integer"},
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
            "text": {"type": "string"},
            "question_type": ref("QuestionType"),
            "answer_type": ref("AnswerType"),
            "possible_answers": array_of({"type": "string"}),
            "correct_answer": {"type": "string"},
            "scores_for_correct_answer": {"type": "integer"},
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
        "oneOf": [ref("QuestionCreate"), array_of(ref("QuestionCreate"))],
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
            "text": {"type": "string"},
            "question_type": ref("QuestionType"),
            "answer_type": ref("AnswerType"),
            "possible_answers": array_of({"type": "string"}),
            "correct_answer": {"type": "string"},
            "scores_for_correct_answer": {"type": "integer"},
        },
    },
    "HomeworkState": {
        "type": "string",
        "enum": ["CL", "OP", "SC"],
        "description": "CL=closed, OP=open, SC=scored",
    },
    "ProjectState": {
        "type": "string",
        "enum": ["CL", "CS", "PR", "CO"],
        "description": (
            "CL=closed, CS=collecting submissions, PR=peer reviewing, "
            "CO=completed"
        ),
    },
    "QuestionType": {
        "type": "string",
        "enum": ["MC", "FF", "FL", "CB"],
    },
    "AnswerType": {
        "type": ["string", "null"],
        "enum": ["ANY", "FLT", "INT", "EXS", "CTS", None],
    },
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
}


PATHS = {
    "/api/health/": {
        "get": operation(
            "api_health",
            ["System"],
            "Health check",
            {"200": response("Service status", ref("Health"))},
            requires_auth=False,
        ),
    },
    "/api/courses/{course_slug}/course-criteria.yaml": {
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
            parameters=[COURSE_SLUG],
            requires_auth=False,
        ),
    },
    "/api/courses/{course_slug}/leaderboard.yaml": {
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
            parameters=[COURSE_SLUG],
            requires_auth=False,
        ),
    },
    "/api/courses/{course_slug}/homeworks/{homework_slug}/submissions": {
        "get": operation(
            "api_homework_submissions_export",
            ["Course Data"],
            "Export homework submissions",
            {
                "200": response("Homework submissions export", JSON),
                "404": response("Course or homework not found", ref("Error")),
            },
            parameters=[COURSE_SLUG, HOMEWORK_SLUG],
        ),
    },
    "/api/courses/{course_slug}/projects/{project_slug}/submissions": {
        "get": operation(
            "api_project_submissions_export",
            ["Course Data"],
            "Export project submissions",
            {
                "200": response("Project submissions export", JSON),
                "404": response("Course or project not found", ref("Error")),
            },
            parameters=[COURSE_SLUG, PROJECT_SLUG],
        ),
    },
    "/api/courses/{course_slug}/graduates": {
        "get": operation(
            "api_course_graduates",
            ["Course Data"],
            "Get course graduates",
            {
                "200": response("Course graduates", ref("Graduates")),
                "404": response("Course not found", ref("Error")),
            },
            parameters=[COURSE_SLUG],
        ),
    },
    "/api/courses/{course_slug}/certificates": {
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
            parameters=[COURSE_SLUG],
            body=request_body(ref("CertificateUpdateRequest")),
            description=(
                "Updates many enrollment certificate URLs in one request. "
                "The response includes per-entry errors for missing users, "
                "unenrolled users, and invalid entries."
            ),
        ),
    },
    "/api/courses/": {
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
    "/api/courses/{course_slug}/": {
        "get": operation(
            "api_course_detail",
            ["Courses"],
            "Get course details",
            {
                "200": response("Course details", ref("CourseDetail")),
                "404": response("Course not found", ref("Error")),
            },
            parameters=[COURSE_SLUG],
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
            parameters=[COURSE_SLUG],
            body=request_body(ref("CoursePatch")),
        ),
    },
    "/api/courses/{course_slug}/homeworks/": {
        "get": operation(
            "api_homeworks",
            ["Homeworks"],
            "List homeworks",
            {"200": response("Homework list", ref("HomeworksList"))},
            parameters=[COURSE_SLUG],
        ),
        "post": operation(
            "api_homeworks",
            ["Homeworks"],
            "Create homework or homeworks",
            {
                "201": response("Created homeworks", ref("HomeworkCreateResponse")),
                "400": response("Invalid request", ref("Error")),
                "404": response("Course not found", ref("Error")),
            },
            parameters=[COURSE_SLUG],
            body=request_body(ref("HomeworkCreateRequest")),
        ),
    },
    "/api/courses/{course_slug}/homeworks/{homework_id}/": {
        "get": operation(
            "api_homework_detail",
            ["Homeworks"],
            "Get homework details",
            {
                "200": response("Homework details", ref("Homework")),
                "404": response("Course or homework not found", ref("Error")),
            },
            parameters=[COURSE_SLUG, HOMEWORK_ID],
        ),
        "patch": operation(
            "api_homework_detail",
            ["Homeworks"],
            "Update homework",
            {
                "200": response("Updated homework", ref("Homework")),
                "400": response("Invalid field, state, or date", ref("Error")),
                "404": response("Course or homework not found", ref("Error")),
            },
            parameters=[COURSE_SLUG, HOMEWORK_ID],
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
                "404": response("Course or homework not found", ref("Error")),
            },
            parameters=[COURSE_SLUG, HOMEWORK_ID],
            description=(
                "Deletes a homework only when state is CL and there are no "
                "submissions. This endpoint never deletes submission data."
            ),
        ),
    },
    "/api/courses/{course_slug}/homeworks/by-slug/{homework_slug}/": {
        "get": operation(
            "api_homework_detail_by_slug",
            ["Homeworks"],
            "Get homework details by slug",
            {
                "200": response("Homework details", ref("Homework")),
                "404": response("Course or homework not found", ref("Error")),
            },
            parameters=[COURSE_SLUG, HOMEWORK_SLUG],
        ),
        "patch": operation(
            "api_homework_detail_by_slug",
            ["Homeworks"],
            "Update homework by slug",
            {
                "200": response("Updated homework", ref("Homework")),
                "400": response("Invalid field, state, or date", ref("Error")),
                "404": response("Course or homework not found", ref("Error")),
            },
            parameters=[COURSE_SLUG, HOMEWORK_SLUG],
            body=request_body(ref("HomeworkPatch")),
        ),
        "put": operation(
            "api_homework_detail_by_slug",
            ["Homeworks"],
            "Create or update homework by slug",
            {
                "200": response("Updated homework", ref("Homework")),
                "201": response("Created homework", ref("Homework")),
                "400": response("Invalid request or replace blocked", ref("Error")),
                "404": response("Course not found", ref("Error")),
            },
            parameters=[COURSE_SLUG, HOMEWORK_SLUG],
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
                "404": response("Course or homework not found", ref("Error")),
            },
            parameters=[COURSE_SLUG, HOMEWORK_SLUG],
            description=(
                "Deletes a homework only when state is CL and there are no "
                "submissions. This endpoint never deletes submission data."
            ),
        ),
    },
    "/api/courses/{course_slug}/projects/": {
        "get": operation(
            "api_projects",
            ["Projects"],
            "List projects",
            {"200": response("Project list", ref("ProjectsList"))},
            parameters=[COURSE_SLUG],
        ),
        "post": operation(
            "api_projects",
            ["Projects"],
            "Create project or projects",
            {
                "201": response("Created projects", ref("ProjectCreateResponse")),
                "400": response("Invalid request", ref("Error")),
                "404": response("Course not found", ref("Error")),
            },
            parameters=[COURSE_SLUG],
            body=request_body(ref("ProjectCreateRequest")),
        ),
    },
    "/api/courses/{course_slug}/projects/{project_id}/": {
        "get": operation(
            "api_project_detail",
            ["Projects"],
            "Get project details",
            {
                "200": response("Project details", ref("Project")),
                "404": response("Course or project not found", ref("Error")),
            },
            parameters=[COURSE_SLUG, PROJECT_ID],
        ),
        "patch": operation(
            "api_project_detail",
            ["Projects"],
            "Update project",
            {
                "200": response("Updated project", ref("Project")),
                "400": response("Invalid field, state, or date", ref("Error")),
                "404": response("Course or project not found", ref("Error")),
            },
            parameters=[COURSE_SLUG, PROJECT_ID],
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
                "404": response("Course or project not found", ref("Error")),
            },
            parameters=[COURSE_SLUG, PROJECT_ID],
            description=(
                "Deletes a project only when state is CL and there are no "
                "submissions. This endpoint never deletes submission data."
            ),
        ),
    },
    "/api/courses/{course_slug}/projects/by-slug/{project_slug}/": {
        "get": operation(
            "api_project_detail_by_slug",
            ["Projects"],
            "Get project details by slug",
            {
                "200": response("Project details", ref("Project")),
                "404": response("Course or project not found", ref("Error")),
            },
            parameters=[COURSE_SLUG, PROJECT_SLUG],
        ),
        "patch": operation(
            "api_project_detail_by_slug",
            ["Projects"],
            "Update project by slug",
            {
                "200": response("Updated project", ref("Project")),
                "400": response("Invalid field, state, or date", ref("Error")),
                "404": response("Course or project not found", ref("Error")),
            },
            parameters=[COURSE_SLUG, PROJECT_SLUG],
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
            parameters=[COURSE_SLUG, PROJECT_SLUG],
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
                "404": response("Course or project not found", ref("Error")),
            },
            parameters=[COURSE_SLUG, PROJECT_SLUG],
            description=(
                "Deletes a project only when state is CL and there are no "
                "submissions. This endpoint never deletes submission data."
            ),
        ),
    },
    "/api/courses/{course_slug}/homeworks/{homework_id}/questions/": {
        "get": operation(
            "api_questions",
            ["Questions"],
            "List homework questions",
            {"200": response("Question list", ref("QuestionsList"))},
            parameters=[COURSE_SLUG, HOMEWORK_ID],
        ),
        "post": operation(
            "api_questions",
            ["Questions"],
            "Create question or questions",
            {
                "201": response("Created questions", ref("QuestionCreateResponse")),
                "400": response("Invalid request", ref("Error")),
                "404": response("Course or homework not found", ref("Error")),
            },
            parameters=[COURSE_SLUG, HOMEWORK_ID],
            body=request_body(ref("QuestionCreateRequest")),
        ),
    },
    "/api/courses/{course_slug}/homeworks/{homework_id}/questions/{question_id}/": {
        "get": operation(
            "api_question_detail",
            ["Questions"],
            "Get question details",
            {
                "200": response("Question details", ref("Question")),
                "404": response("Question not found", ref("Error")),
            },
            parameters=[COURSE_SLUG, HOMEWORK_ID, QUESTION_ID],
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
            parameters=[COURSE_SLUG, HOMEWORK_ID, QUESTION_ID],
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
            parameters=[COURSE_SLUG, HOMEWORK_ID, QUESTION_ID],
            description=(
                "Deletes a question only when it has no answers. This "
                "endpoint never deletes submitted answer data."
            ),
        ),
    },
}


def build_openapi_spec():
    paths = deepcopy(PATHS)

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
