from courses.models.homework import Question
from courses.models.homework import AnswerTypes, HomeworkState
from courses.models.project import ProjectState

from ..primitives import choices_schema, enum_schema

HOMEWORK_STATE_SCHEMA = enum_schema(
    HomeworkState,
    description="CL=closed, OP=open, SC=scored",
)
PROJECT_STATE_SCHEMA = enum_schema(
    ProjectState,
    description=(
        "CL=closed, CS=collecting submissions, PR=peer reviewing, "
        "CO=completed"
    ),
)
QUESTION_TYPE_SCHEMA = choices_schema(Question.QUESTION_TYPES)
ANSWER_TYPE_SCHEMA = enum_schema(AnswerTypes, nullable=True)

CONTENT_ENUM_SCHEMAS = {
    "HomeworkState": HOMEWORK_STATE_SCHEMA,
    "ProjectState": PROJECT_STATE_SCHEMA,
    "QuestionType": QUESTION_TYPE_SCHEMA,
    "AnswerType": ANSWER_TYPE_SCHEMA,
}
