from . import course, project, homework, wrapped  # noqa: F401

from django.contrib.auth import get_user_model

from .course import (
    Course,
    CourseRegistration,
    Enrollment,
    LeaderboardComplaint,
    RegistrationCampaign,
)
from .homework import (
    Answer,
    AnswerTypes,
    Homework,
    HomeworkState,
    HomeworkStatistics,
    QUESTION_ANSWER_DELIMITER,
    Question,
    QuestionTypes,
    Submission,
)
from .project import (
    CriteriaResponse,
    PeerReview,
    PeerReviewState,
    Project,
    ProjectEvaluationScore,
    ProjectState,
    ProjectStatistics,
    ProjectSubmission,
    ProjectVote,
    ReviewCriteria,
    ReviewCriteriaTypes,
)
from .wrapped import UserWrappedStatistics, WrappedStatistics

User = get_user_model()

__all__ = (
    "Answer",
    "AnswerTypes",
    "Course",
    "CourseRegistration",
    "CriteriaResponse",
    "Enrollment",
    "Homework",
    "HomeworkState",
    "HomeworkStatistics",
    "LeaderboardComplaint",
    "PeerReview",
    "PeerReviewState",
    "Project",
    "ProjectEvaluationScore",
    "ProjectState",
    "ProjectStatistics",
    "ProjectSubmission",
    "ProjectVote",
    "QUESTION_ANSWER_DELIMITER",
    "Question",
    "QuestionTypes",
    "RegistrationCampaign",
    "ReviewCriteria",
    "ReviewCriteriaTypes",
    "Submission",
    "User",
    "UserWrappedStatistics",
    "WrappedStatistics",
)
