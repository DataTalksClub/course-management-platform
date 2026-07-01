from dataclasses import dataclass

from django.shortcuts import get_object_or_404

from api.crud import get_course_child_or_404
from api.safety import require_staff_token
from courses.models import Course, Project


@dataclass(frozen=True)
class ProjectActionRouteData:
    request: object
    course_slug: str
    project_id: int | None = None
    project_slug: str | None = None


def project_for_action(data):
    course = get_object_or_404(Course, slug=data.course_slug)
    project = get_course_child_or_404(
        Project,
        course,
        object_id=data.project_id,
        slug=data.project_slug,
    )
    return project


def project_action_route_response(data, action):
    staff_error = require_staff_token(data.request)
    if staff_error:
        return staff_error

    project = project_for_action(data)
    response = action(project)
    return response
