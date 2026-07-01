from ..primitives import (
    OperationData,
    operation,
    ref,
    request_body,
    response,
)


PROJECT_PATHS_BY_URL_NAME = {
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
    }

}
