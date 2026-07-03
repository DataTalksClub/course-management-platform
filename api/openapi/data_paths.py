from .primitives import (
    JSON,
    OperationData,
    content_response,
    operation,
    response,
    schema_request_body,
    schema_response,
)

API_HEALTH_SUCCESS_RESPONSE = schema_response("Service status", "Health")
COURSE_NOT_FOUND_RESPONSE = schema_response("Course not found", "Error")
COURSE_OR_HOMEWORK_NOT_FOUND_RESPONSE = schema_response(
    "Course or homework not found",
    "Error",
)
COURSE_OR_PROJECT_NOT_FOUND_RESPONSE = schema_response(
    "Course or project not found",
    "Error",
)
INVALID_REQUEST_RESPONSE = schema_response("Invalid request", "Error")
INVALID_EVENT_PAYLOAD_RESPONSE = schema_response(
    "Invalid event payload",
    "Error",
)
INVALID_WEBHOOK_TOKEN_RESPONSE = schema_response(
    "Invalid webhook token",
    "Error",
)
WEBHOOK_NOT_CONFIGURED_RESPONSE = schema_response(
    "Webhook not configured",
    "Error",
)

API_HEALTH_RESPONSES = {"200": API_HEALTH_SUCCESS_RESPONSE}
API_HEALTH_DATA = OperationData(
    "api_health",
    ["System"],
    "Health check",
    API_HEALTH_RESPONSES,
    requires_auth=False,
)
API_HEALTH_OPERATION = operation(API_HEALTH_DATA)

COURSE_CRITERIA_CONTENT = {"text/yaml": {"schema": {"type": "string"}}}
COURSE_CRITERIA_SUCCESS_RESPONSE = content_response(
    "Course criteria YAML",
    COURSE_CRITERIA_CONTENT,
)
COURSE_CRITERIA_RESPONSES = {
    "200": COURSE_CRITERIA_SUCCESS_RESPONSE,
    "404": COURSE_NOT_FOUND_RESPONSE,
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
COURSE_LEADERBOARD_SUCCESS_RESPONSE = content_response(
    "Leaderboard YAML",
    COURSE_LEADERBOARD_CONTENT,
)
COURSE_LEADERBOARD_RESPONSES = {
    "200": COURSE_LEADERBOARD_SUCCESS_RESPONSE,
    "404": COURSE_NOT_FOUND_RESPONSE,
}
COURSE_LEADERBOARD_DATA = OperationData(
    "api_course_leaderboard",
    ["Course Data"],
    "Get leaderboard YAML",
    COURSE_LEADERBOARD_RESPONSES,
    requires_auth=False,
)
COURSE_LEADERBOARD_OPERATION = operation(COURSE_LEADERBOARD_DATA)

HOMEWORK_SUBMISSIONS_EXPORT_SUCCESS_RESPONSE = response(
    "Homework submissions export",
    JSON,
)
HOMEWORK_SUBMISSIONS_EXPORT_RESPONSES = {
    "200": HOMEWORK_SUBMISSIONS_EXPORT_SUCCESS_RESPONSE,
    "404": COURSE_OR_HOMEWORK_NOT_FOUND_RESPONSE,
}
HOMEWORK_SUBMISSIONS_EXPORT_DATA = OperationData(
    "api_homework_submissions_export",
    ["Course Data"],
    "Export homework submissions",
    HOMEWORK_SUBMISSIONS_EXPORT_RESPONSES,
)
HOMEWORK_SUBMISSIONS_EXPORT_OPERATION = operation(HOMEWORK_SUBMISSIONS_EXPORT_DATA)

PROJECT_SUBMISSIONS_EXPORT_SUCCESS_RESPONSE = response(
    "Project submissions export",
    JSON,
)
PROJECT_SUBMISSIONS_EXPORT_RESPONSES = {
    "200": PROJECT_SUBMISSIONS_EXPORT_SUCCESS_RESPONSE,
    "404": COURSE_OR_PROJECT_NOT_FOUND_RESPONSE,
}
PROJECT_SUBMISSIONS_EXPORT_DATA = OperationData(
    "api_project_submissions_export",
    ["Course Data"],
    "Export project submissions",
    PROJECT_SUBMISSIONS_EXPORT_RESPONSES,
)
PROJECT_SUBMISSIONS_EXPORT_OPERATION = operation(PROJECT_SUBMISSIONS_EXPORT_DATA)

COURSE_GRADUATES_SUCCESS_RESPONSE = schema_response(
    "Course graduates",
    "Graduates",
)
COURSE_GRADUATES_RESPONSES = {
    "200": COURSE_GRADUATES_SUCCESS_RESPONSE,
    "404": COURSE_NOT_FOUND_RESPONSE,
}
COURSE_GRADUATES_DATA = OperationData(
    "api_course_graduates",
    ["Course Data"],
    "Get course graduates",
    COURSE_GRADUATES_RESPONSES,
)
COURSE_GRADUATES_OPERATION = operation(COURSE_GRADUATES_DATA)

COURSE_CERTIFICATES_SUCCESS_RESPONSE = schema_response(
    "Certificate update result",
    "CertificateUpdateResponse",
)
COURSE_CERTIFICATES_RESPONSES = {
    "200": COURSE_CERTIFICATES_SUCCESS_RESPONSE,
    "400": INVALID_REQUEST_RESPONSE,
    "404": COURSE_NOT_FOUND_RESPONSE,
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

DATAMAILER_EVENTS_SUCCESS_RESPONSE = schema_response(
    "Datamailer event accepted",
    "DatamailerEventAccepted",
)
DATAMAILER_EVENTS_RESPONSES = {
    "200": DATAMAILER_EVENTS_SUCCESS_RESPONSE,
    "400": INVALID_EVENT_PAYLOAD_RESPONSE,
    "401": INVALID_WEBHOOK_TOKEN_RESPONSE,
    "503": WEBHOOK_NOT_CONFIGURED_RESPONSE,
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

DATAMAILER_SEND_AUDITS_SUCCESS_RESPONSE = schema_response(
    "Datamailer send audits",
    "DatamailerSendAudits",
)
DATAMAILER_SEND_AUDITS_RESPONSES = {
    "200": DATAMAILER_SEND_AUDITS_SUCCESS_RESPONSE,
}
DATAMAILER_SEND_AUDITS_PARAMETERS = [
    {
        "name": "email",
        "in": "query",
        "required": False,
        "schema": {"type": "string"},
    },
    {
        "name": "template_key",
        "in": "query",
        "required": False,
        "schema": {"type": "string"},
    },
    {
        "name": "idempotency_key",
        "in": "query",
        "required": False,
        "schema": {"type": "string"},
    },
    {
        "name": "limit",
        "in": "query",
        "required": False,
        "schema": {"type": "integer", "default": 25, "maximum": 100},
    },
]
DATAMAILER_SEND_AUDITS_DESCRIPTION = (
    "Lists CMP's own Datamailer send-audit rows (one per send attempt "
    "through the outbox -> dispatch -> /api/transactional/send pipeline). "
    "Each row's response_payload carries the message summary and, when the "
    "send ran with Datamailer's dry_run flag, the rendered subject/bodies. "
    "Used by the e2e smoke suite to verify the rendered email over HTTP "
    "without delivering anything. Ordered newest first."
)
DATAMAILER_SEND_AUDITS_DATA = OperationData(
    "api_datamailer_send_audits",
    ["Datamailer"],
    "List Datamailer send audits",
    DATAMAILER_SEND_AUDITS_RESPONSES,
    parameters=DATAMAILER_SEND_AUDITS_PARAMETERS,
    description=DATAMAILER_SEND_AUDITS_DESCRIPTION,
)
DATAMAILER_SEND_AUDITS_OPERATION = operation(DATAMAILER_SEND_AUDITS_DATA)

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
    "api_datamailer_send_audits": {
        "get": DATAMAILER_SEND_AUDITS_OPERATION,
    },
}
