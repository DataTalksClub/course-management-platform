from ..primitives import (
    OperationData,
    operation,
    ref,
    request_body,
    response,
)


PROJECTS_LIST_REF = ref("ProjectsList")
PROJECT_CREATE_RESPONSE_REF = ref("ProjectCreateResponse")
PROJECT_CREATE_REQUEST_REF = ref("ProjectCreateRequest")
PROJECT_REF = ref("Project")
PROJECT_PATCH_REF = ref("ProjectPatch")
PROJECT_UPSERT_REF = ref("ProjectUpsert")
PROJECT_ASSIGN_REVIEWS_RESPONSE_REF = ref("ProjectAssignReviewsResponse")
PROJECT_SCORE_RESPONSE_REF = ref("ProjectScoreResponse")
DELETED_REF = ref("Deleted")
ERROR_REF = ref("Error")

PROJECTS_LIST_RESPONSES = {
    "200": response("Project list", PROJECTS_LIST_REF),
}
PROJECTS_LIST_DATA = OperationData(
    "api_projects",
    ["Projects"],
    "List projects",
    PROJECTS_LIST_RESPONSES,
)
PROJECTS_LIST_OPERATION = operation(PROJECTS_LIST_DATA)

PROJECT_CREATE_RESPONSES = {
    "201": response("Created projects", PROJECT_CREATE_RESPONSE_REF),
    "400": response("Invalid request", ERROR_REF),
    "404": response("Course not found", ERROR_REF),
}
PROJECT_CREATE_BODY = request_body(PROJECT_CREATE_REQUEST_REF)
PROJECT_CREATE_DATA = OperationData(
    "api_projects",
    ["Projects"],
    "Create project or projects",
    PROJECT_CREATE_RESPONSES,
    body=PROJECT_CREATE_BODY,
)
PROJECT_CREATE_OPERATION = operation(PROJECT_CREATE_DATA)

PROJECT_DETAIL_RESPONSES = {
    "200": response("Project details", PROJECT_REF),
    "404": response("Course or project not found", ERROR_REF),
}
PROJECT_DETAIL_DATA = OperationData(
    "api_project_detail",
    ["Projects"],
    "Get project details",
    PROJECT_DETAIL_RESPONSES,
)
PROJECT_DETAIL_OPERATION = operation(PROJECT_DETAIL_DATA)

PROJECT_PATCH_RESPONSES = {
    "200": response("Updated project", PROJECT_REF),
    "400": response("Invalid field, state, or date", ERROR_REF),
    "404": response("Course or project not found", ERROR_REF),
}
PROJECT_PATCH_BODY = request_body(PROJECT_PATCH_REF)
PROJECT_PATCH_DATA = OperationData(
    "api_project_detail",
    ["Projects"],
    "Update project",
    PROJECT_PATCH_RESPONSES,
    body=PROJECT_PATCH_BODY,
)
PROJECT_PATCH_OPERATION = operation(PROJECT_PATCH_DATA)

PROJECT_DELETE_RESPONSES = {
    "200": response("Deleted", DELETED_REF),
    "400": response(
        "Project is not closed or has submissions",
        ERROR_REF,
    ),
    "404": response("Course or project not found", ERROR_REF),
}
PROJECT_DELETE_DESCRIPTION = (
    "Deletes a project only when state is CL and there are no "
    "submissions. This endpoint never deletes submission data."
)
PROJECT_DELETE_DATA = OperationData(
    "api_project_detail",
    ["Projects"],
    "Delete project",
    PROJECT_DELETE_RESPONSES,
    description=PROJECT_DELETE_DESCRIPTION,
)
PROJECT_DELETE_OPERATION = operation(PROJECT_DELETE_DATA)

PROJECT_ASSIGN_REVIEWS_RESPONSES = {
    "200": response(
        "Peer reviews assigned",
        PROJECT_ASSIGN_REVIEWS_RESPONSE_REF,
    ),
    "400": response("Assignment blocked", PROJECT_ASSIGN_REVIEWS_RESPONSE_REF),
    "403": response("Staff token required", ERROR_REF),
    "404": response("Course or project not found", ERROR_REF),
}
PROJECT_ASSIGN_REVIEWS_DESCRIPTION = (
    "Assigns peer reviews with the same safeguards as cadmin: "
    "project state must be CS, submission due date must be in "
    "the past, and enough submissions must exist."
)
PROJECT_ASSIGN_REVIEWS_DATA = OperationData(
    "api_project_assign_reviews",
    ["Projects"],
    "Assign project peer reviews",
    PROJECT_ASSIGN_REVIEWS_RESPONSES,
    description=PROJECT_ASSIGN_REVIEWS_DESCRIPTION,
)
PROJECT_ASSIGN_REVIEWS_OPERATION = operation(PROJECT_ASSIGN_REVIEWS_DATA)

PROJECT_SCORE_RESPONSES = {
    "200": response("Project scored", PROJECT_SCORE_RESPONSE_REF),
    "400": response("Scoring blocked", PROJECT_SCORE_RESPONSE_REF),
    "403": response("Staff token required", ERROR_REF),
    "404": response("Course or project not found", ERROR_REF),
}
PROJECT_SCORE_DESCRIPTION = (
    "Scores project submissions with the same safeguards as "
    "cadmin: project state must be PR, peer review due date "
    "must be in the past, and peer reviews must exist."
)
PROJECT_SCORE_DATA = OperationData(
    "api_project_score",
    ["Projects"],
    "Score project",
    PROJECT_SCORE_RESPONSES,
    description=PROJECT_SCORE_DESCRIPTION,
)
PROJECT_SCORE_OPERATION = operation(PROJECT_SCORE_DATA)

PROJECT_DETAIL_BY_SLUG_DATA = OperationData(
    "api_project_detail_by_slug",
    ["Projects"],
    "Get project details by slug",
    PROJECT_DETAIL_RESPONSES,
)
PROJECT_DETAIL_BY_SLUG_OPERATION = operation(PROJECT_DETAIL_BY_SLUG_DATA)

PROJECT_PATCH_BY_SLUG_DATA = OperationData(
    "api_project_detail_by_slug",
    ["Projects"],
    "Update project by slug",
    PROJECT_PATCH_RESPONSES,
    body=PROJECT_PATCH_BODY,
)
PROJECT_PATCH_BY_SLUG_OPERATION = operation(PROJECT_PATCH_BY_SLUG_DATA)

PROJECT_UPSERT_RESPONSES = {
    "200": response("Updated project", PROJECT_REF),
    "201": response("Created project", PROJECT_REF),
    "400": response("Invalid request", ERROR_REF),
    "404": response("Course not found", ERROR_REF),
}
PROJECT_UPSERT_BODY = request_body(PROJECT_UPSERT_REF)
PROJECT_UPSERT_DESCRIPTION = (
    "Idempotently creates or updates a project using the slug in "
    "the path."
)
PROJECT_UPSERT_DATA = OperationData(
    "api_project_detail_by_slug",
    ["Projects"],
    "Create or update project by slug",
    PROJECT_UPSERT_RESPONSES,
    body=PROJECT_UPSERT_BODY,
    description=PROJECT_UPSERT_DESCRIPTION,
)
PROJECT_UPSERT_OPERATION = operation(PROJECT_UPSERT_DATA)

PROJECT_DELETE_BY_SLUG_DATA = OperationData(
    "api_project_detail_by_slug",
    ["Projects"],
    "Delete project by slug",
    PROJECT_DELETE_RESPONSES,
    description=PROJECT_DELETE_DESCRIPTION,
)
PROJECT_DELETE_BY_SLUG_OPERATION = operation(PROJECT_DELETE_BY_SLUG_DATA)

PROJECT_ASSIGN_REVIEWS_BY_SLUG_DATA = OperationData(
    "api_project_assign_reviews_by_slug",
    ["Projects"],
    "Assign project peer reviews by slug",
    PROJECT_ASSIGN_REVIEWS_RESPONSES,
    description=PROJECT_ASSIGN_REVIEWS_DESCRIPTION,
)
PROJECT_ASSIGN_REVIEWS_BY_SLUG_OPERATION = operation(
    PROJECT_ASSIGN_REVIEWS_BY_SLUG_DATA
)

PROJECT_SCORE_BY_SLUG_DATA = OperationData(
    "api_project_score_by_slug",
    ["Projects"],
    "Score project by slug",
    PROJECT_SCORE_RESPONSES,
    description=PROJECT_SCORE_DESCRIPTION,
)
PROJECT_SCORE_BY_SLUG_OPERATION = operation(PROJECT_SCORE_BY_SLUG_DATA)

PROJECT_PATHS_BY_URL_NAME = {
    "api_projects": {
        "get": PROJECTS_LIST_OPERATION,
        "post": PROJECT_CREATE_OPERATION,
    },
    "api_project_detail": {
        "get": PROJECT_DETAIL_OPERATION,
        "patch": PROJECT_PATCH_OPERATION,
        "delete": PROJECT_DELETE_OPERATION,
    },
    "api_project_assign_reviews": {
        "post": PROJECT_ASSIGN_REVIEWS_OPERATION,
    },
    "api_project_score": {
        "post": PROJECT_SCORE_OPERATION,
    },
    "api_project_detail_by_slug": {
        "get": PROJECT_DETAIL_BY_SLUG_OPERATION,
        "patch": PROJECT_PATCH_BY_SLUG_OPERATION,
        "put": PROJECT_UPSERT_OPERATION,
        "delete": PROJECT_DELETE_BY_SLUG_OPERATION,
    },
    "api_project_assign_reviews_by_slug": {
        "post": PROJECT_ASSIGN_REVIEWS_BY_SLUG_OPERATION,
    },
    "api_project_score_by_slug": {
        "post": PROJECT_SCORE_BY_SLUG_OPERATION,
    }

}
