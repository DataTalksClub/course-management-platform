from .courses import courses_list_view, course_detail_view
from .homeworks import (
    homeworks_view,
    homework_detail_view,
    homework_detail_by_slug_view,
)
from .projects import (
    projects_view,
    project_detail_view,
    project_detail_by_slug_view,
)
from .questions import questions_view, question_detail_view
from .registration_campaigns import (
    registration_campaign_detail_view,
    registration_campaign_registrations_view,
    registration_campaigns_view,
)

__all__ = [
    "courses_list_view",
    "course_detail_view",
    "homeworks_view",
    "homework_detail_view",
    "homework_detail_by_slug_view",
    "projects_view",
    "project_detail_view",
    "project_detail_by_slug_view",
    "questions_view",
    "question_detail_view",
    "registration_campaigns_view",
    "registration_campaign_detail_view",
    "registration_campaign_registrations_view",
]
