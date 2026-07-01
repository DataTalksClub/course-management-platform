from dataclasses import dataclass

from django.http import JsonResponse

from courses.models.project import Project, ProjectState

from api.safety import apply_patch_fields, error_response
from api.utils import instructions_url_error, parse_date
from api.views.project_serializers import project_to_dict
from api.views.project_upsert_rules import (
    PROJECT_PATCH_FIELDS,
    PROJECT_PATCH_RULES,
)
from api.views.project_upsert_validation import project_upsert_title


@dataclass(frozen=True)
class ProjectUpsertCreateData:
    course: object
    slug: str
    title: str
    description: str
    instructions_url: str | None
    submission_due_date: object
    peer_review_due_date: object
    state: str


def project_by_slug(course, project_slug):
    project = Project.objects.filter(
        course=course,
        slug=project_slug,
    ).first()
    return project, project is None


def project_upsert_create_data(course, project_slug, data):
    title = project_upsert_title(data)
    description = data.get("description", "")
    instructions_url = data.get("instructions_url")
    submission_due_date = parse_date(data["submission_due_date"])
    peer_review_due_date = parse_date(data["peer_review_due_date"])
    values = {
        "course": course,
        "slug": project_slug,
        "title": title,
        "description": description,
        "instructions_url": instructions_url,
        "submission_due_date": submission_due_date,
        "peer_review_due_date": peer_review_due_date,
        "state": ProjectState.CLOSED.value,
    }
    create_data = ProjectUpsertCreateData(**values)
    return create_data


def create_project_from_upsert(course, project_slug, data):
    create_data = project_upsert_create_data(course, project_slug, data)
    create_data_vars = vars(create_data)
    values = create_data_vars.copy()
    project = Project.objects.create(**values)
    return project


def apply_project_title(project, data):
    name = data.get("name")
    title = data.get("title", name)
    if title is not None:
        project.title = title


def apply_project_description(project, data):
    if "description" in data:
        project.description = data["description"]


def apply_project_instructions_url(project, data):
    if "instructions_url" not in data:
        return None

    instructions_url = data["instructions_url"]
    error = instructions_url_error(instructions_url)
    if error:
        return error_response(
            error,
            "invalid_instructions_url",
            details={"field": "instructions_url"},
        )

    project.instructions_url = instructions_url
    return None


def project_generic_patch_data(data):
    handled = {"title", "name", "description", "instructions_url"}
    patch_data = {}
    for key, value in data.items():
        if key in PROJECT_PATCH_FIELDS and key not in handled:
            patch_data[key] = value
    return patch_data


def apply_project_data(project, data):
    apply_project_title(project, data)
    apply_project_description(project, data)

    error = apply_project_instructions_url(project, data)
    if error:
        return error

    patch_data = project_generic_patch_data(data)
    return apply_patch_fields(
        project,
        patch_data,
        PROJECT_PATCH_RULES,
    )


def save_project_upsert(project, data, created):
    error = apply_project_data(project, data)
    if error:
        return error

    project.save()
    project_data = project_to_dict(project)
    if created:
        response_status = 201
    else:
        response_status = 200
    response = JsonResponse(
        project_data, status=response_status
    )
    return response
