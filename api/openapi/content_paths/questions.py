from ..primitives import (
    OperationData,
    operation,
    ref,
    request_body,
    response,
)


QUESTION_PATHS_BY_URL_NAME = {
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
    }

}
