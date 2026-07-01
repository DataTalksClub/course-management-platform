from .primitives import (
    JSON,
    OperationData,
    content_response,
    operation,
    response,
    schema_request_body,
    schema_response,
)


DATA_PATHS_BY_URL_NAME = {
    "api_health": {
        "get": operation(
            OperationData(
                "api_health",
                ["System"],
                "Health check",
                {"200": schema_response("Service status", "Health")},
                requires_auth=False,
            )
        ),
    },
    "api_course_criteria_yaml": {
        "get": operation(
            OperationData(
                "api_course_criteria_yaml",
                ["Course Data"],
                "Get course criteria YAML",
                {
                    "200": content_response(
                        "Course criteria YAML",
                        {"text/yaml": {"schema": {"type": "string"}}},
                    ),
                    "404": schema_response("Course not found", "Error"),
                },
                requires_auth=False,
            )
        ),
    },
    "api_course_leaderboard": {
        "get": operation(
            OperationData(
                "api_course_leaderboard",
                ["Course Data"],
                "Get leaderboard YAML",
                {
                    "200": content_response(
                        "Leaderboard YAML",
                        {"text/plain": {"schema": {"type": "string"}}},
                    ),
                    "404": schema_response("Course not found", "Error"),
                },
                requires_auth=False,
            )
        ),
    },
    "api_homework_submissions_export": {
        "get": operation(
            OperationData(
                "api_homework_submissions_export",
                ["Course Data"],
                "Export homework submissions",
                {
                    "200": response(
                        "Homework submissions export", JSON
                    ),
                    "404": schema_response(
                        "Course or homework not found", "Error"
                    ),
                },
            )
        ),
    },
    "api_project_submissions_export": {
        "get": operation(
            OperationData(
                "api_project_submissions_export",
                ["Course Data"],
                "Export project submissions",
                {
                    "200": response("Project submissions export", JSON),
                    "404": schema_response(
                        "Course or project not found", "Error"
                    ),
                },
            )
        ),
    },
    "api_course_graduates": {
        "get": operation(
            OperationData(
                "api_course_graduates",
                ["Course Data"],
                "Get course graduates",
                {
                    "200": schema_response(
                        "Course graduates", "Graduates"
                    ),
                    "404": schema_response("Course not found", "Error"),
                },
            )
        ),
    },
    "api_course_certificates": {
        "post": operation(
            OperationData(
                "api_course_certificates",
                ["Course Data"],
                "Bulk update enrollment certificate URLs",
                {
                    "200": schema_response(
                        "Certificate update result",
                        "CertificateUpdateResponse",
                    ),
                    "400": schema_response("Invalid request", "Error"),
                    "404": schema_response("Course not found", "Error"),
                },
                body=schema_request_body("CertificateUpdateRequest"),
                description=(
                    "Updates many enrollment certificate URLs in one request. "
                    "The response includes per-entry errors for missing users, "
                    "unenrolled users, and invalid entries."
                ),
            )
        ),
    },
    "api_datamailer_events": {
        "post": operation(
            OperationData(
                "api_datamailer_events",
                ["Datamailer"],
                "Receive Datamailer contact event",
                {
                    "200": schema_response(
                        "Datamailer event accepted",
                        "DatamailerEventAccepted",
                    ),
                    "400": schema_response(
                        "Invalid event payload", "Error"
                    ),
                    "401": schema_response(
                        "Invalid webhook token", "Error"
                    ),
                    "503": schema_response(
                        "Webhook not configured", "Error"
                    ),
                },
                body=schema_request_body("DatamailerEvent"),
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
            )
        ),
    },
}
