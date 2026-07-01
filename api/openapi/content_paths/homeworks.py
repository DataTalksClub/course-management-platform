from ..primitives import (
    OperationData,
    operation,
    ref,
    request_body,
    response,
)


HOMEWORK_PATHS_BY_URL_NAME = {
    "api_homeworks": {
        "get": operation(
            OperationData(
                "api_homeworks",
                ["Homeworks"],
                "List homeworks",
                {
                    "200": response(
                        "Homework list", ref("HomeworksList")
                    )
                },
            )
        ),
        "post": operation(
            OperationData(
                "api_homeworks",
                ["Homeworks"],
                "Create homework or homeworks",
                {
                    "201": response(
                        "Created homeworks",
                        ref("HomeworkCreateResponse"),
                    ),
                    "400": response("Invalid request", ref("Error")),
                    "404": response("Course not found", ref("Error")),
                },
                body=request_body(ref("HomeworkCreateRequest")),
            )
        ),
    },
    "api_homework_detail": {
        "get": operation(
            OperationData(
                "api_homework_detail",
                ["Homeworks"],
                "Get homework details",
                {
                    "200": response(
                        "Homework details", ref("Homework")
                    ),
                    "404": response(
                        "Course or homework not found", ref("Error")
                    ),
                },
            )
        ),
        "patch": operation(
            OperationData(
                "api_homework_detail",
                ["Homeworks"],
                "Update homework",
                {
                    "200": response(
                        "Updated homework", ref("Homework")
                    ),
                    "400": response(
                        "Invalid field, state, or date", ref("Error")
                    ),
                    "404": response(
                        "Course or homework not found", ref("Error")
                    ),
                },
                body=request_body(ref("HomeworkPatch")),
            )
        ),
        "delete": operation(
            OperationData(
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
            )
        ),
    },
    "api_homework_score": {
        "post": operation(
            OperationData(
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
                    "403": response(
                        "Staff token required", ref("Error")
                    ),
                    "404": response(
                        "Course or homework not found", ref("Error")
                    ),
                },
                description=(
                    "Scores homework submissions with the same safeguards as "
                    "cadmin: due date must be in the past, state must be OP, "
                    "and already scored homeworks are rejected."
                ),
            )
        ),
    },
    "api_homework_detail_by_slug": {
        "get": operation(
            OperationData(
                "api_homework_detail_by_slug",
                ["Homeworks"],
                "Get homework details by slug",
                {
                    "200": response(
                        "Homework details", ref("Homework")
                    ),
                    "404": response(
                        "Course or homework not found", ref("Error")
                    ),
                },
            )
        ),
        "patch": operation(
            OperationData(
                "api_homework_detail_by_slug",
                ["Homeworks"],
                "Update homework by slug",
                {
                    "200": response(
                        "Updated homework", ref("Homework")
                    ),
                    "400": response(
                        "Invalid field, state, or date", ref("Error")
                    ),
                    "404": response(
                        "Course or homework not found", ref("Error")
                    ),
                },
                body=request_body(ref("HomeworkPatch")),
            )
        ),
        "put": operation(
            OperationData(
                "api_homework_detail_by_slug",
                ["Homeworks"],
                "Create or update homework by slug",
                {
                    "200": response(
                        "Updated homework", ref("Homework")
                    ),
                    "201": response(
                        "Created homework", ref("Homework")
                    ),
                    "400": response(
                        "Invalid request or replace blocked",
                        ref("Error"),
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
            )
        ),
        "delete": operation(
            OperationData(
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
            )
        ),
    },
    "api_homework_score_by_slug": {
        "post": operation(
            OperationData(
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
                    "403": response(
                        "Staff token required", ref("Error")
                    ),
                    "404": response(
                        "Course or homework not found", ref("Error")
                    ),
                },
                description=(
                    "Scores homework submissions with the same safeguards as "
                    "cadmin: due date must be in the past, state must be OP, "
                    "and already scored homeworks are rejected."
                ),
            )
        ),
    }

}
