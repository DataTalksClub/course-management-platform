from dataclasses import dataclass
from datetime import date

from django.http import JsonResponse
from django.utils.text import slugify

from courses.models import Project
from courses.models.project import ProjectState

from api.crud import bulk_create_response
from api.safety import require_staff_token
from api.utils import instructions_url_error, parse_date, parse_json_body
from api.views.project_serializers import project_to_dict


@dataclass(frozen=True)
class ProjectCreateRequiredValues:
    name: str
    submission_due_str: str
    peer_review_due_str: str


@dataclass(frozen=True)
class ProjectCreateValues:
    name: str
    instructions_url: str | None
    submission_due_date: date
    peer_review_due_date: date


@dataclass(frozen=True)
class ProjectDueDates:
    submission_due_date: date
    peer_review_due_date: date


def project_create_required_values(project_data):
    name = project_data.get("name")
    submission_due_str = project_data.get("submission_due_date")
    peer_review_due_str = project_data.get("peer_review_due_date")
    if not name or not submission_due_str or not peer_review_due_str:
        return (
            None,
            "name, submission_due_date, and peer_review_due_date are required",
        )

    values = ProjectCreateRequiredValues(
        name=name,
        submission_due_str=submission_due_str,
        peer_review_due_str=peer_review_due_str,
    )
    return values, None


def project_instructions_url_error(project_data):
    instructions_url = project_data.get("instructions_url")
    if instructions_url:
        return instructions_url_error(instructions_url)
    return None


def project_create_instructions_url(project_data):
    instructions_url = project_data.get("instructions_url")
    error = project_instructions_url_error(project_data)
    if error:
        return None, error

    return instructions_url, None


def parse_project_due_dates(submission_due_str, peer_review_due_str):
    submission_due_date = parse_date(submission_due_str)
    if submission_due_date is None:
        return None, f"Invalid date format: {submission_due_str}"

    peer_review_due_date = parse_date(peer_review_due_str)
    if peer_review_due_date is None:
        return None, f"Invalid date format: {peer_review_due_str}"

    due_dates = ProjectDueDates(
        submission_due_date=submission_due_date,
        peer_review_due_date=peer_review_due_date,
    )
    return due_dates, None


def project_slug(project_data, name):
    slug = project_data.get("slug")
    if slug:
        return slug
    generated_slug = slugify(name)
    return generated_slug


def project_duplicate_error(course, slug):
    if Project.objects.filter(course=course, slug=slug).exists():
        return f"Project with slug '{slug}' already exists"
    return None


def project_create_slug(course, project_data, name):
    slug = project_slug(project_data, name)
    error = project_duplicate_error(course, slug)
    if error:
        return None, error

    return slug, None


def project_create_attrs(course, project_data):
    required_values, error = project_create_required_values(project_data)
    if error:
        return None, error

    instructions_url, error = project_create_instructions_url(project_data)
    if error:
        return None, error

    due_dates, error = parse_project_due_dates(
        required_values.submission_due_str,
        required_values.peer_review_due_str,
    )
    if error:
        return None, error

    values = ProjectCreateValues(
        name=required_values.name,
        instructions_url=instructions_url,
        submission_due_date=due_dates.submission_due_date,
        peer_review_due_date=due_dates.peer_review_due_date,
    )
    return project_create_attrs_from_values(
        course,
        project_data,
        values,
    )


def project_create_attrs_from_values(
    course,
    project_data,
    values,
):
    slug, error = project_create_slug(course, project_data, values.name)
    if error:
        return None, error

    attrs = project_create_defaults(project_data, values)
    attrs["slug"] = slug
    return attrs, None


def project_create_defaults(
    project_data,
    values,
):
    return {
        "title": values.name,
        "description": project_data.get("description", ""),
        "instructions_url": values.instructions_url,
        "submission_due_date": values.submission_due_date,
        "peer_review_due_date": values.peer_review_due_date,
        "state": ProjectState.CLOSED.value,
    }


def create_project(course, project_data):
    attrs, error = project_create_attrs(course, project_data)
    if error:
        return None, error

    project = Project.objects.create(
        course=course,
        **attrs,
    )

    return project_to_dict(project), None


def projects_list_response(course):
    projects = Project.objects.filter(course=course).order_by("id")
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
