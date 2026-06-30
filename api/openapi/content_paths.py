from .primitives import (
    OperationData,
    operation,
    ref,
    request_body,
    response,
)


CONTENT_PATHS_BY_URL_NAME = {
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
    },
    "api_projects": {
        "get": operation(
            OperationData(
                "api_projects",
                ["Projects"],
                "List projects",
                {"200": response("Project list", ref("ProjectsList"))},
            )
        ),
        "post": operation(
            OperationData(
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
            )
        ),
    },
    "api_project_detail": {
        "get": operation(
            OperationData(
                "api_project_detail",
                ["Projects"],
                "Get project details",
                {
                    "200": response("Project details", ref("Project")),
                    "404": response(
                        "Course or project not found", ref("Error")
                    ),
                },
            )
        ),
        "patch": operation(
            OperationData(
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
            )
        ),
        "delete": operation(
            OperationData(
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
            )
        ),
    },
    "api_project_assign_reviews": {
        "post": operation(
            OperationData(
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
                    "403": response(
                        "Staff token required", ref("Error")
                    ),
                    "404": response(
                        "Course or project not found", ref("Error")
                    ),
                },
                description=(
                    "Assigns peer reviews with the same safeguards as cadmin: "
                    "project state must be CS, submission due date must be in "
                    "the past, and enough submissions must exist."
                ),
            )
        ),
    },
    "api_project_score": {
        "post": operation(
            OperationData(
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
                    "403": response(
                        "Staff token required", ref("Error")
                    ),
                    "404": response(
                        "Course or project not found", ref("Error")
                    ),
                },
                description=(
                    "Scores project submissions with the same safeguards as "
                    "cadmin: project state must be PR, peer review due date "
                    "must be in the past, and peer reviews must exist."
                ),
            )
        ),
    },
    "api_project_detail_by_slug": {
        "get": operation(
            OperationData(
                "api_project_detail_by_slug",
                ["Projects"],
                "Get project details by slug",
                {
                    "200": response("Project details", ref("Project")),
                    "404": response(
                        "Course or project not found", ref("Error")
                    ),
                },
            )
        ),
        "patch": operation(
            OperationData(
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
            )
        ),
        "put": operation(
            OperationData(
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
            )
        ),
        "delete": operation(
            OperationData(
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
            )
        ),
    },
    "api_project_assign_reviews_by_slug": {
        "post": operation(
            OperationData(
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
                    "403": response(
                        "Staff token required", ref("Error")
                    ),
                    "404": response(
                        "Course or project not found", ref("Error")
                    ),
                },
                description=(
                    "Assigns peer reviews with the same safeguards as cadmin: "
                    "project state must be CS, submission due date must be in "
                    "the past, and enough submissions must exist."
                ),
            )
        ),
    },
    "api_project_score_by_slug": {
        "post": operation(
            OperationData(
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
                    "403": response(
                        "Staff token required", ref("Error")
                    ),
                    "404": response(
                        "Course or project not found", ref("Error")
                    ),
                },
                description=(
                    "Scores project submissions with the same safeguards as "
                    "cadmin: project state must be PR, peer review due date "
                    "must be in the past, and peer reviews must exist."
                ),
            )
        ),
    },
    "api_questions": {
        "get": operation(
            OperationData(
                "api_questions",
                ["Questions"],
                "List homework questions",
                {
                    "200": response(
                        "Question list", ref("QuestionsList")
                    )
                },
            )
        ),
        "post": operation(
            OperationData(
                "api_questions",
                ["Questions"],
                "Create question or questions",
                {
                    "201": response(
                        "Created questions",
                        ref("QuestionCreateResponse"),
                    ),
                    "400": response("Invalid request", ref("Error")),
                    "404": response(
                        "Course or homework not found", ref("Error")
                    ),
                },
                body=request_body(ref("QuestionCreateRequest")),
            )
        ),
    },
    "api_question_detail": {
        "get": operation(
            OperationData(
                "api_question_detail",
                ["Questions"],
                "Get question details",
                {
                    "200": response(
                        "Question details", ref("Question")
                    ),
                    "404": response("Question not found", ref("Error")),
                },
            )
        ),
        "patch": operation(
            OperationData(
                "api_question_detail",
                ["Questions"],
                "Update question",
                {
                    "200": response(
                        "Updated question", ref("Question")
                    ),
                    "400": response("Invalid field", ref("Error")),
                    "404": response("Question not found", ref("Error")),
                },
                body=request_body(ref("QuestionPatch")),
            )
        ),
        "delete": operation(
            OperationData(
                "api_question_detail",
                ["Questions"],
                "Delete question",
                {
                    "200": response("Deleted", ref("Deleted")),
                    "400": response(
                        "Question has answers", ref("Error")
                    ),
                    "404": response("Question not found", ref("Error")),
                },
                description=(
                    "Deletes a question only when it has no answers. This "
                    "endpoint never deletes submitted answer data."
                ),
            )
        ),
    },
}
