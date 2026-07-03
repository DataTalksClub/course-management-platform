from dataclasses import dataclass
from datetime import datetime

from django.db.models import Count
from django.http import JsonResponse
from django.utils.text import slugify

from courses.models.project import Project
from courses.models.project import ProjectState

from api.crud import bulk_create_response
from api.safety import require_staff_token
from api.utils import instructions_url_error, parse_date, parse_json_body
from api.views.project_serializers import project_to_dict


@dataclass(frozen=True)
class ProjectCreateInput:
    name: str
    submission_due_str: str
    peer_review_due_str: str


@dataclass(frozen=True)
class ProjectCreateDates:
    submission_due_date: datetime
    peer_review_due_date: datetime


@dataclass(frozen=True)
class ProjectCreateValues:
    input_data: ProjectCreateInput
    instructions_url: str | None
    dates: ProjectCreateDates
    slug: str


def project_create_instructions_url(project_data):
    instructions_url = project_data.get("instructions_url")
    if not instructions_url:
        return instructions_url, None

    error = instructions_url_error(instructions_url)
    if error:
        return None, error

    return instructions_url, None


def project_create_slug(course, project_data, name):
    slug = project_data.get("slug")
    if not slug:
        slug = slugify(name)

    matching_project = Project.objects.filter(course=course, slug=slug)
    slug_exists = matching_project.exists()
    if slug_exists:
        error = f"Project with slug '{slug}' already exists"
        return None, error

    return slug, None


def project_create_input(project_data):
    name = project_data.get("name")
    submission_due_str = project_data.get("submission_due_date")
    peer_review_due_str = project_data.get("peer_review_due_date")
    if not name or not submission_due_str or not peer_review_due_str:
        error = (
            "name, submission_due_date, and "
            "peer_review_due_date are required"
        )
        return None, error

    input_data = ProjectCreateInput(
        name=name,
        submission_due_str=submission_due_str,
        peer_review_due_str=peer_review_due_str,
    )
    return input_data, None


def project_create_dates(input_data):
    submission_due_date = parse_date(input_data.submission_due_str)
    if submission_due_date is None:
        error = f"Invalid date format: {input_data.submission_due_str}"
        return None, error

    peer_review_due_date = parse_date(input_data.peer_review_due_str)
    if peer_review_due_date is None:
        error = f"Invalid date format: {input_data.peer_review_due_str}"
        return None, error

    dates = ProjectCreateDates(
        submission_due_date=submission_due_date,
        peer_review_due_date=peer_review_due_date,
    )
    return dates, None


def project_create_values(course, project_data):
    input_data, error = project_create_input(project_data)
    if error:
        return None, error

    instructions_url, error = project_create_instructions_url(project_data)
    if error:
        return None, error

    dates, error = project_create_dates(input_data)
    if error:
        return None, error

    slug, error = project_create_slug(course, project_data, input_data.name)
    if error:
        return None, error

    values = ProjectCreateValues(
        input_data=input_data,
        instructions_url=instructions_url,
        dates=dates,
        slug=slug,
    )
    return values, None


def project_model_attrs(project_data, values):
    description = project_data.get("description", "")
    attrs = {
        "title": values.input_data.name,
        "description": description,
        "instructions_url": values.instructions_url,
        "submission_due_date": values.dates.submission_due_date,
        "peer_review_due_date": values.dates.peer_review_due_date,
        "state": ProjectState.CLOSED.value,
        "slug": values.slug,
    }
    return attrs


def create_project(course, project_data):
    values, error = project_create_values(course, project_data)
    if error:
        return None, error

    attrs = project_model_attrs(project_data, values)
    project = Project.objects.create(
        course=course,
        **attrs,
    )

    project_record = project_to_dict(project)
    return project_record, None


def projects_list_response(course):
    projects = (
        Project.objects.filter(course=course)
        .annotate(submission_count=Count("projectsubmission"))
        .order_by("id")
    )
    project_records = []
    for project in projects:
        project_record = project_to_dict(project)
        project_records.append(project_record)

    payload = {
        "projects": project_records,
    }
    response = JsonResponse(payload)
    return response


def projects_create_response(request, course):
    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    data, err = parse_json_body(request)
    if err:
        return err

    response = bulk_create_response(data, create_project, course)
    return response
