from dataclasses import dataclass

from django.shortcuts import get_object_or_404

from api.crud import get_course_child_or_404
from api.safety import require_staff_token
from api.views.project_actions import (
    project_assign_reviews_enqueue_response,
    project_assign_reviews_status_response,
    project_score_enqueue_response,
    project_score_status_response,
)
from courses.models.course import Course
from courses.models.project import Project


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


def project_async_action_route_response(data, enqueue, status):
    """Async variant: POST enqueues a background job, GET reports status."""
    staff_error = require_staff_token(data.request)
    if staff_error:
        return staff_error

    project = project_for_action(data)
    if data.request.method == "GET":
        return status(project)
    return enqueue(data.request, project)


def project_assign_reviews_route_response(data):
    return project_async_action_route_response(
        data,
        project_assign_reviews_enqueue_response,
        project_assign_reviews_status_response,
    )


def project_score_route_response(data):
    return project_async_action_route_response(
        data,
        project_score_enqueue_response,
        project_score_status_response,
    )
