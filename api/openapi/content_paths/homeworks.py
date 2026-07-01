from ..primitives import (
    OperationData,
    operation,
    ref,
    request_body,
    response,
)


HOMEWORKS_LIST_REF = ref("HomeworksList")
HOMEWORK_CREATE_RESPONSE_REF = ref("HomeworkCreateResponse")
HOMEWORK_CREATE_REQUEST_REF = ref("HomeworkCreateRequest")
HOMEWORK_REF = ref("Homework")
HOMEWORK_PATCH_REF = ref("HomeworkPatch")
HOMEWORK_UPSERT_REF = ref("HomeworkUpsert")
HOMEWORK_SCORE_RESPONSE_REF = ref("HomeworkScoreResponse")
DELETED_REF = ref("Deleted")
ERROR_REF = ref("Error")

HOMEWORKS_LIST_RESPONSES = {
    "200": response("Homework list", HOMEWORKS_LIST_REF),
}
HOMEWORKS_LIST_DATA = OperationData(
    "api_homeworks",
    ["Homeworks"],
    "List homeworks",
    HOMEWORKS_LIST_RESPONSES,
)
HOMEWORKS_LIST_OPERATION = operation(HOMEWORKS_LIST_DATA)

HOMEWORK_CREATE_RESPONSES = {
    "201": response("Created homeworks", HOMEWORK_CREATE_RESPONSE_REF),
    "400": response("Invalid request", ERROR_REF),
    "404": response("Course not found", ERROR_REF),
}
HOMEWORK_CREATE_BODY = request_body(HOMEWORK_CREATE_REQUEST_REF)
HOMEWORK_CREATE_DATA = OperationData(
    "api_homeworks",
    ["Homeworks"],
    "Create homework or homeworks",
    HOMEWORK_CREATE_RESPONSES,
    body=HOMEWORK_CREATE_BODY,
)
HOMEWORK_CREATE_OPERATION = operation(HOMEWORK_CREATE_DATA)

HOMEWORK_DETAIL_RESPONSES = {
    "200": response("Homework details", HOMEWORK_REF),
    "404": response("Course or homework not found", ERROR_REF),
}
HOMEWORK_DETAIL_DATA = OperationData(
    "api_homework_detail",
    ["Homeworks"],
    "Get homework details",
    HOMEWORK_DETAIL_RESPONSES,
)
HOMEWORK_DETAIL_OPERATION = operation(HOMEWORK_DETAIL_DATA)

HOMEWORK_PATCH_RESPONSES = {
    "200": response("Updated homework", HOMEWORK_REF),
    "400": response("Invalid field, state, or date", ERROR_REF),
    "404": response("Course or homework not found", ERROR_REF),
}
HOMEWORK_PATCH_BODY = request_body(HOMEWORK_PATCH_REF)
HOMEWORK_PATCH_DATA = OperationData(
    "api_homework_detail",
    ["Homeworks"],
    "Update homework",
    HOMEWORK_PATCH_RESPONSES,
    body=HOMEWORK_PATCH_BODY,
)
HOMEWORK_PATCH_OPERATION = operation(HOMEWORK_PATCH_DATA)

HOMEWORK_DELETE_RESPONSES = {
    "200": response("Deleted", DELETED_REF),
    "400": response(
        "Homework is not closed or has submissions",
        ERROR_REF,
    ),
    "404": response("Course or homework not found", ERROR_REF),
}
HOMEWORK_DELETE_DESCRIPTION = (
    "Deletes a homework only when state is CL and there are no "
    "submissions. This endpoint never deletes submission data."
)
HOMEWORK_DELETE_DATA = OperationData(
    "api_homework_detail",
    ["Homeworks"],
    "Delete homework",
    HOMEWORK_DELETE_RESPONSES,
    description=HOMEWORK_DELETE_DESCRIPTION,
)
HOMEWORK_DELETE_OPERATION = operation(HOMEWORK_DELETE_DATA)

HOMEWORK_SCORE_RESPONSES = {
    "200": response("Homework scored", HOMEWORK_SCORE_RESPONSE_REF),
    "400": response("Scoring blocked", HOMEWORK_SCORE_RESPONSE_REF),
    "403": response("Staff token required", ERROR_REF),
    "404": response("Course or homework not found", ERROR_REF),
}
HOMEWORK_SCORE_DESCRIPTION = (
    "Scores homework submissions with the same safeguards as "
    "cadmin: due date must be in the past, state must be OP, "
    "and already scored homeworks are rejected."
)
HOMEWORK_SCORE_DATA = OperationData(
    "api_homework_score",
    ["Homeworks"],
    "Score homework submissions",
    HOMEWORK_SCORE_RESPONSES,
    description=HOMEWORK_SCORE_DESCRIPTION,
)
HOMEWORK_SCORE_OPERATION = operation(HOMEWORK_SCORE_DATA)

HOMEWORK_DETAIL_BY_SLUG_DATA = OperationData(
    "api_homework_detail_by_slug",
    ["Homeworks"],
    "Get homework details by slug",
    HOMEWORK_DETAIL_RESPONSES,
)
HOMEWORK_DETAIL_BY_SLUG_OPERATION = operation(HOMEWORK_DETAIL_BY_SLUG_DATA)

HOMEWORK_PATCH_BY_SLUG_DATA = OperationData(
    "api_homework_detail_by_slug",
    ["Homeworks"],
    "Update homework by slug",
    HOMEWORK_PATCH_RESPONSES,
    body=HOMEWORK_PATCH_BODY,
)
HOMEWORK_PATCH_BY_SLUG_OPERATION = operation(HOMEWORK_PATCH_BY_SLUG_DATA)

HOMEWORK_UPSERT_RESPONSES = {
    "200": response("Updated homework", HOMEWORK_REF),
    "201": response("Created homework", HOMEWORK_REF),
    "400": response("Invalid request or replace blocked", ERROR_REF),
    "404": response("Course not found", ERROR_REF),
}
HOMEWORK_UPSERT_BODY = request_body(HOMEWORK_UPSERT_REF)
HOMEWORK_UPSERT_DESCRIPTION = (
    "Idempotently creates or updates a homework using the slug in "
    "the path. If questions are supplied for an existing homework, "
    "they replace current questions only when the homework is "
    "closed and has no submissions."
)
HOMEWORK_UPSERT_DATA = OperationData(
    "api_homework_detail_by_slug",
    ["Homeworks"],
    "Create or update homework by slug",
    HOMEWORK_UPSERT_RESPONSES,
    body=HOMEWORK_UPSERT_BODY,
    description=HOMEWORK_UPSERT_DESCRIPTION,
)
HOMEWORK_UPSERT_OPERATION = operation(HOMEWORK_UPSERT_DATA)

HOMEWORK_DELETE_BY_SLUG_DATA = OperationData(
    "api_homework_detail_by_slug",
    ["Homeworks"],
    "Delete homework by slug",
    HOMEWORK_DELETE_RESPONSES,
    description=HOMEWORK_DELETE_DESCRIPTION,
)
HOMEWORK_DELETE_BY_SLUG_OPERATION = operation(HOMEWORK_DELETE_BY_SLUG_DATA)

HOMEWORK_SCORE_BY_SLUG_DATA = OperationData(
    "api_homework_score_by_slug",
    ["Homeworks"],
    "Score homework submissions by slug",
    HOMEWORK_SCORE_RESPONSES,
    description=HOMEWORK_SCORE_DESCRIPTION,
)
HOMEWORK_SCORE_BY_SLUG_OPERATION = operation(HOMEWORK_SCORE_BY_SLUG_DATA)

HOMEWORK_PATHS_BY_URL_NAME = {
    "api_homeworks": {
        "get": HOMEWORKS_LIST_OPERATION,
        "post": HOMEWORK_CREATE_OPERATION,
    },
    "api_homework_detail": {
        "get": HOMEWORK_DETAIL_OPERATION,
        "patch": HOMEWORK_PATCH_OPERATION,
        "delete": HOMEWORK_DELETE_OPERATION,
    },
    "api_homework_score": {
        "post": HOMEWORK_SCORE_OPERATION,
    },
    "api_homework_detail_by_slug": {
        "get": HOMEWORK_DETAIL_BY_SLUG_OPERATION,
        "patch": HOMEWORK_PATCH_BY_SLUG_OPERATION,
        "put": HOMEWORK_UPSERT_OPERATION,
        "delete": HOMEWORK_DELETE_BY_SLUG_OPERATION,
    },
    "api_homework_score_by_slug": {
        "post": HOMEWORK_SCORE_BY_SLUG_OPERATION,
    }

}
