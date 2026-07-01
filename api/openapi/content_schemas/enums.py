from courses.models.homework import Question
from courses.models.homework import AnswerTypes, HomeworkState
from courses.models.project import ProjectState

from ..primitives import choices_schema, enum_schema


CONTENT_ENUM_SCHEMAS = {
    "HomeworkState": enum_schema(
        HomeworkState,
        description="CL=closed, OP=open, SC=scored",
    ),
    "ProjectState": enum_schema(
        ProjectState,
        description=(
            "CL=closed, CS=collecting submissions, PR=peer reviewing, "
            "CO=completed"
        ),
    ),
    "QuestionType": choices_schema(Question.QUESTION_TYPES),
    "AnswerType": enum_schema(AnswerTypes, nullable=True)
}
