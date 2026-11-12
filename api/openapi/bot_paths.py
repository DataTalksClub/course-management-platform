from .primitives import JSON, response


BOT_PATHS_BY_URL_NAME = {
    "api_bot_course_state": {
        "get": {
            "operationId": "api_bot_course_state",
            "x-django-url-name": "api_bot_course_state",
            "tags": ["Bot Context"],
            "summary": "Read current course state without write authority",
            "description": (
                "Use an exact visible cohort slug. Returns schema_version, "
                "fetched_at, course, homeworks, projects and student. "
                "Public items contain titles, states, stored dates and source_url. "
                "Projects also have peer_review_open, assignments_created and "
                "peer_review_opens_at (null: CMP has no opening schedule). "
                "Both Slack parameters are optional but must be paired. "
                "Exact linked TEAM_USER identity returns student.mapped and "
                "per-project assigned_count/pending_count; otherwise mapped=false. "
                "Never include student in public answers or public LLM context. "
                "Responses are private/no-store. No writes are supported."
            ),
            "security": [{"BotReadAuth": []}],
            "parameters": [
                {"name": name, "in": "query", "required": False,
                 "schema": {"type": "string"}}
                for name in ("slack_team_id", "slack_user_id")
            ],
            "responses": {
                "200": response("Current course state and optional private counts", JSON),
                "400": response("Invalid or incomplete Slack identity", JSON),
                "401": response("Missing or invalid dedicated bot read token", JSON),
                "404": response("Unknown or hidden course", JSON),
                "405": response("Only GET is supported"),
            },
        }
    }
}
