from .primitives import (
    JSON,
    OperationData,
    content_response,
    operation,
    response,
    schema_request_body,
    schema_response,
)

API_HEALTH_RESPONSES = {"200": schema_response("Service status", "Health")}
API_HEALTH_DATA = OperationData(
    "api_health",
    ["System"],
    "Health check",
    API_HEALTH_RESPONSES,
    requires_auth=False,
)
API_HEALTH_OPERATION = operation(API_HEALTH_DATA)

COURSE_CRITERIA_CONTENT = {"text/yaml": {"schema": {"type": "string"}}}
COURSE_CRITERIA_RESPONSES = {
    "200": content_response("Course criteria YAML", COURSE_CRITERIA_CONTENT),
    "404": schema_response("Course not found", "Error"),
}
COURSE_CRITERIA_DATA = OperationData(
    "api_course_criteria_yaml",
    ["Course Data"],
    "Get course criteria YAML",
    COURSE_CRITERIA_RESPONSES,
    requires_auth=False,
)
COURSE_CRITERIA_OPERATION = operation(COURSE_CRITERIA_DATA)

COURSE_LEADERBOARD_CONTENT = {"text/plain": {"schema": {"type": "string"}}}
COURSE_LEADERBOARD_RESPONSES = {
    "200": content_response("Leaderboard YAML", COURSE_LEADERBOARD_CONTENT),
    "404": schema_response("Course not found", "Error"),
}
COURSE_LEADERBOARD_DATA = OperationData(
    "api_course_leaderboard",
    ["Course Data"],
    "Get leaderboard YAML",
    COURSE_LEADERBOARD_RESPONSES,
    requires_auth=False,
)
COURSE_LEADERBOARD_OPERATION = operation(COURSE_LEADERBOARD_DATA)

HOMEWORK_SUBMISSIONS_EXPORT_RESPONSES = {
    "200": response("Homework submissions export", JSON),
    "404": schema_response("Course or homework not found", "Error"),
}
HOMEWORK_SUBMISSIONS_EXPORT_DATA = OperationData(
    "api_homework_submissions_export",
    ["Course Data"],
    "Export homework submissions",
    HOMEWORK_SUBMISSIONS_EXPORT_RESPONSES,
)
HOMEWORK_SUBMISSIONS_EXPORT_OPERATION = operation(HOMEWORK_SUBMISSIONS_EXPORT_DATA)

PROJECT_SUBMISSIONS_EXPORT_RESPONSES = {
    "200": response("Project submissions export", JSON),
    "404": schema_response("Course or project not found", "Error"),
}
PROJECT_SUBMISSIONS_EXPORT_DATA = OperationData(
    "api_project_submissions_export",
    ["Course Data"],
    "Export project submissions",
    PROJECT_SUBMISSIONS_EXPORT_RESPONSES,
)
PROJECT_SUBMISSIONS_EXPORT_OPERATION = operation(PROJECT_SUBMISSIONS_EXPORT_DATA)

COURSE_GRADUATES_RESPONSES = {
    "200": schema_response("Course graduates", "Graduates"),
    "404": schema_response("Course not found", "Error"),
}
COURSE_GRADUATES_DATA = OperationData(
    "api_course_graduates",
    ["Course Data"],
    "Get course graduates",
    COURSE_GRADUATES_RESPONSES,
)
COURSE_GRADUATES_OPERATION = operation(COURSE_GRADUATES_DATA)

COURSE_CERTIFICATES_RESPONSES = {
    "200": schema_response(
        "Certificate update result",
        "CertificateUpdateResponse",
    ),
    "400": schema_response("Invalid request", "Error"),
    "404": schema_response("Course not found", "Error"),
}
COURSE_CERTIFICATES_BODY = schema_request_body("CertificateUpdateRequest")
COURSE_CERTIFICATES_DESCRIPTION = (
    "Updates many enrollment certificate URLs in one request. "
    "The response includes per-entry errors for missing users, "
    "unenrolled users, and invalid entries."
)
COURSE_CERTIFICATES_DATA = OperationData(
    "api_course_certificates",
    ["Course Data"],
    "Bulk update enrollment certificate URLs",
    COURSE_CERTIFICATES_RESPONSES,
    body=COURSE_CERTIFICATES_BODY,
    description=COURSE_CERTIFICATES_DESCRIPTION,
)
COURSE_CERTIFICATES_OPERATION = operation(COURSE_CERTIFICATES_DATA)

DATAMAILER_EVENTS_RESPONSES = {
    "200": schema_response(
        "Datamailer event accepted",
        "DatamailerEventAccepted",
    ),
    "400": schema_response("Invalid event payload", "Error"),
    "401": schema_response("Invalid webhook token", "Error"),
    "503": schema_response("Webhook not configured", "Error"),
}
DATAMAILER_EVENTS_BODY = schema_request_body("DatamailerEvent")
DATAMAILER_EVENTS_DESCRIPTION = (
    "Webhook used by Datamailer to report hard bounces, "
    "complaints, subscription changes, skipped/failed sends, and "
    "message lifecycle events back to CMP for support and audit "
    "visibility. CMP records these callbacks but does not use them "
    "as its email preference store. The request must include the "
    "configured Datamailer webhook token in the Authorization "
    "bearer token or X-Datamailer-Webhook-Token header."
)
DATAMAILER_EVENTS_DATA = OperationData(
    "api_datamailer_events",
    ["Datamailer"],
    "Receive Datamailer contact event",
    DATAMAILER_EVENTS_RESPONSES,
    body=DATAMAILER_EVENTS_BODY,
    requires_auth=False,
    description=DATAMAILER_EVENTS_DESCRIPTION,
)
DATAMAILER_EVENTS_OPERATION = operation(DATAMAILER_EVENTS_DATA)

DATA_PATHS_BY_URL_NAME = {
    "api_health": {
        "get": API_HEALTH_OPERATION,
    },
    "api_course_criteria_yaml": {
        "get": COURSE_CRITERIA_OPERATION,
    },
    "api_course_leaderboard": {
        "get": COURSE_LEADERBOARD_OPERATION,
    },
    "api_homework_submissions_export": {
        "get": HOMEWORK_SUBMISSIONS_EXPORT_OPERATION,
    },
    "api_project_submissions_export": {
        "get": PROJECT_SUBMISSIONS_EXPORT_OPERATION,
    },
    "api_course_graduates": {
        "get": COURSE_GRADUATES_OPERATION,
    },
    "api_course_certificates": {
        "post": COURSE_CERTIFICATES_OPERATION,
    },
    "api_datamailer_events": {
        "post": DATAMAILER_EVENTS_OPERATION,
    },
}
