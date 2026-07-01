from ..primitives import (
    OperationData,
    operation,
    ref,
    request_body,
    response,
)


QUESTIONS_LIST_REF = ref("QuestionsList")
QUESTION_CREATE_RESPONSE_REF = ref("QuestionCreateResponse")
QUESTION_CREATE_REQUEST_REF = ref("QuestionCreateRequest")
QUESTION_REF = ref("Question")
QUESTION_PATCH_REF = ref("QuestionPatch")
DELETED_REF = ref("Deleted")
ERROR_REF = ref("Error")

QUESTIONS_LIST_RESPONSES = {
    "200": response("Question list", QUESTIONS_LIST_REF),
}
QUESTIONS_LIST_DATA = OperationData(
    "api_questions",
    ["Questions"],
    "List homework questions",
    QUESTIONS_LIST_RESPONSES,
)
QUESTIONS_LIST_OPERATION = operation(QUESTIONS_LIST_DATA)

QUESTION_CREATE_RESPONSES = {
    "201": response("Created questions", QUESTION_CREATE_RESPONSE_REF),
    "400": response("Invalid request", ERROR_REF),
    "404": response("Course or homework not found", ERROR_REF),
}
QUESTION_CREATE_BODY = request_body(QUESTION_CREATE_REQUEST_REF)
QUESTION_CREATE_DATA = OperationData(
    "api_questions",
    ["Questions"],
    "Create question or questions",
    QUESTION_CREATE_RESPONSES,
    body=QUESTION_CREATE_BODY,
)
QUESTION_CREATE_OPERATION = operation(QUESTION_CREATE_DATA)

QUESTION_DETAIL_RESPONSES = {
    "200": response("Question details", QUESTION_REF),
    "404": response("Question not found", ERROR_REF),
}
QUESTION_DETAIL_DATA = OperationData(
    "api_question_detail",
    ["Questions"],
    "Get question details",
    QUESTION_DETAIL_RESPONSES,
)
QUESTION_DETAIL_OPERATION = operation(QUESTION_DETAIL_DATA)

QUESTION_PATCH_RESPONSES = {
    "200": response("Updated question", QUESTION_REF),
    "400": response("Invalid field", ERROR_REF),
    "404": response("Question not found", ERROR_REF),
}
QUESTION_PATCH_BODY = request_body(QUESTION_PATCH_REF)
QUESTION_PATCH_DATA = OperationData(
    "api_question_detail",
    ["Questions"],
    "Update question",
    QUESTION_PATCH_RESPONSES,
    body=QUESTION_PATCH_BODY,
)
QUESTION_PATCH_OPERATION = operation(QUESTION_PATCH_DATA)

QUESTION_DELETE_RESPONSES = {
    "200": response("Deleted", DELETED_REF),
    "400": response("Question has answers", ERROR_REF),
    "404": response("Question not found", ERROR_REF),
}
QUESTION_DELETE_DESCRIPTION = (
    "Deletes a question only when it has no answers. This "
    "endpoint never deletes submitted answer data."
)
QUESTION_DELETE_DATA = OperationData(
    "api_question_detail",
    ["Questions"],
    "Delete question",
    QUESTION_DELETE_RESPONSES,
    description=QUESTION_DELETE_DESCRIPTION,
)
QUESTION_DELETE_OPERATION = operation(QUESTION_DELETE_DATA)

QUESTION_PATHS_BY_URL_NAME = {
    "api_questions": {
        "get": QUESTIONS_LIST_OPERATION,
        "post": QUESTION_CREATE_OPERATION,
    },
    "api_question_detail": {
        "get": QUESTION_DETAIL_OPERATION,
        "patch": QUESTION_PATCH_OPERATION,
        "delete": QUESTION_DELETE_OPERATION,
    }

}
