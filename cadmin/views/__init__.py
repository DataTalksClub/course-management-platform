from .campaigns import (
    campaign_create,
    campaign_edit,
    campaign_registrations,
)
from .course_admin import course_admin, course_list
from .datamailer import datamailer_events, datamailer_operations
from .enrollment import (
    enrollment_edit,
    enrollments_list,
    leaderboard_complaint_resolve,
    leaderboard_complaints,
)
from .homework import (
    homework_clear_correct_answers,
    homework_score,
    homework_set_correct_answers,
    homework_submission_edit,
    homework_submissions,
)
from .projects import (
    project_assign_reviews,
    project_score,
    project_submission_edit,
    project_submissions,
)

__all__ = [
    "campaign_create",
    "campaign_edit",
    "campaign_registrations",
    "course_admin",
    "course_list",
    "datamailer_events",
    "datamailer_operations",
    "enrollment_edit",
    "enrollments_list",
    "homework_clear_correct_answers",
    "homework_score",
    "homework_set_correct_answers",
    "homework_submission_edit",
    "homework_submissions",
    "leaderboard_complaint_resolve",
    "leaderboard_complaints",
    "project_assign_reviews",
    "project_score",
    "project_submission_edit",
    "project_submissions",
]
