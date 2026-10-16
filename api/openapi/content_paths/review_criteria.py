from ..primitives import (
    OperationData,
    operation,
    ref,
    request_body,
    response,
)


REVIEW_CRITERIA_LIST_REF = ref("ReviewCriteriaList")
REVIEW_CRITERIA_CREATE_RESPONSE_REF = ref("ReviewCriteriaCreateResponse")
REVIEW_CRITERIA_CREATE_REQUEST_REF = ref("ReviewCriteriaCreateRequest")
REVIEW_CRITERIA_REF = ref("ReviewCriteria")
REVIEW_CRITERIA_PATCH_REF = ref("ReviewCriteriaPatch")
DELETED_REF = ref("Deleted")
ERROR_REF = ref("Error")
REVIEW_CRITERIA_LIST_SUCCESS_RESPONSE = response(
    "Review criteria list", REVIEW_CRITERIA_LIST_REF
)
REVIEW_CRITERIA_CREATE_SUCCESS_RESPONSE = response(
    "Created review criteria",
    REVIEW_CRITERIA_CREATE_RESPONSE_REF,
)
INVALID_REQUEST_RESPONSE = response("Invalid request", ERROR_REF)
COURSE_NOT_FOUND_RESPONSE = response(
    "Course not found",
    ERROR_REF,
)
REVIEW_CRITERIA_DETAIL_SUCCESS_RESPONSE = response(
    "Review criteria details", REVIEW_CRITERIA_REF
)
REVIEW_CRITERIA_NOT_FOUND_RESPONSE = response(
    "Review criteria not found", ERROR_REF
)
REVIEW_CRITERIA_PATCH_SUCCESS_RESPONSE = response(
    "Updated review criteria", REVIEW_CRITERIA_REF
)
INVALID_FIELD_RESPONSE = response("Invalid field", ERROR_REF)
REVIEW_CRITERIA_DELETE_SUCCESS_RESPONSE = response("Deleted", DELETED_REF)
REVIEW_CRITERIA_HAS_SCORES_RESPONSE = response(
    "Review criteria has scores", ERROR_REF
)

REVIEW_CRITERIA_LIST_RESPONSES = {
    "200": REVIEW_CRITERIA_LIST_SUCCESS_RESPONSE,
}
REVIEW_CRITERIA_LIST_DATA = OperationData(
    "api_review_criteria",
    ["ReviewCriteria"],
    "List course review criteria",
    REVIEW_CRITERIA_LIST_RESPONSES,
)
REVIEW_CRITERIA_LIST_OPERATION = operation(REVIEW_CRITERIA_LIST_DATA)

REVIEW_CRITERIA_CREATE_RESPONSES = {
    "201": REVIEW_CRITERIA_CREATE_SUCCESS_RESPONSE,
    "400": INVALID_REQUEST_RESPONSE,
    "404": COURSE_NOT_FOUND_RESPONSE,
}
REVIEW_CRITERIA_CREATE_BODY = request_body(
    REVIEW_CRITERIA_CREATE_REQUEST_REF
)
REVIEW_CRITERIA_CREATE_DATA = OperationData(
    "api_review_criteria",
    ["ReviewCriteria"],
    "Create review criterion or criteria",
    REVIEW_CRITERIA_CREATE_RESPONSES,
    body=REVIEW_CRITERIA_CREATE_BODY,
)
REVIEW_CRITERIA_CREATE_OPERATION = operation(REVIEW_CRITERIA_CREATE_DATA)

REVIEW_CRITERIA_DETAIL_RESPONSES = {
    "200": REVIEW_CRITERIA_DETAIL_SUCCESS_RESPONSE,
    "404": REVIEW_CRITERIA_NOT_FOUND_RESPONSE,
}
REVIEW_CRITERIA_DETAIL_DATA = OperationData(
    "api_review_criteria_detail",
    ["ReviewCriteria"],
    "Get review criteria details",
    REVIEW_CRITERIA_DETAIL_RESPONSES,
)
REVIEW_CRITERIA_DETAIL_OPERATION = operation(REVIEW_CRITERIA_DETAIL_DATA)

REVIEW_CRITERIA_PATCH_RESPONSES = {
    "200": REVIEW_CRITERIA_PATCH_SUCCESS_RESPONSE,
    "400": INVALID_FIELD_RESPONSE,
    "404": REVIEW_CRITERIA_NOT_FOUND_RESPONSE,
}
REVIEW_CRITERIA_PATCH_BODY = request_body(REVIEW_CRITERIA_PATCH_REF)
REVIEW_CRITERIA_PATCH_DATA = OperationData(
    "api_review_criteria_detail",
    ["ReviewCriteria"],
    "Update review criteria",
    REVIEW_CRITERIA_PATCH_RESPONSES,
    body=REVIEW_CRITERIA_PATCH_BODY,
)
REVIEW_CRITERIA_PATCH_OPERATION = operation(REVIEW_CRITERIA_PATCH_DATA)

REVIEW_CRITERIA_DELETE_RESPONSES = {
    "200": REVIEW_CRITERIA_DELETE_SUCCESS_RESPONSE,
    "400": REVIEW_CRITERIA_HAS_SCORES_RESPONSE,
    "404": REVIEW_CRITERIA_NOT_FOUND_RESPONSE,
}
REVIEW_CRITERIA_DELETE_DESCRIPTION = (
    "Deletes review criteria only when no evaluation scores reference "
    "them. This endpoint never deletes recorded score data."
)
REVIEW_CRITERIA_DELETE_DATA = OperationData(
    "api_review_criteria_detail",
    ["ReviewCriteria"],
    "Delete review criteria",
    REVIEW_CRITERIA_DELETE_RESPONSES,
    description=REVIEW_CRITERIA_DELETE_DESCRIPTION,
)
REVIEW_CRITERIA_DELETE_OPERATION = operation(REVIEW_CRITERIA_DELETE_DATA)

REVIEW_CRITERIA_PATHS_BY_URL_NAME = {
    "api_review_criteria": {
        "get": REVIEW_CRITERIA_LIST_OPERATION,
        "post": REVIEW_CRITERIA_CREATE_OPERATION,
    },
    "api_review_criteria_detail": {
        "get": REVIEW_CRITERIA_DETAIL_OPERATION,
        "patch": REVIEW_CRITERIA_PATCH_OPERATION,
        "delete": REVIEW_CRITERIA_DELETE_OPERATION,
    }
}
