from django.http import JsonResponse
from django.utils.text import slugify

from courses.models.project import Project
from courses.models.project import ProjectState

from api.crud import bulk_create_response
from api.safety import require_staff_token
from api.utils import instructions_url_error, parse_date, parse_json_body
from api.views.project_serializers import project_to_dict


def project_create_instructions_url(project_data):
    instructions_url = project_data.get("instructions_url")
    if not instructions_url:
        return instructions_url, None

    error = instructions_url_error(instructions_url)
    if error:
        return None, error

    return instructions_url, None


def project_slug(project_data, name):
    slug = project_data.get("slug")
    if slug:
        return slug
    generated_slug = slugify(name)
    return generated_slug


def project_duplicate_error(course, slug):
    matching_project = Project.objects.filter(course=course, slug=slug)
    slug_exists = matching_project.exists()
    if slug_exists:
        return f"Project with slug '{slug}' already exists"
    return None


def project_create_slug(course, project_data, name):
    slug = project_slug(project_data, name)
    error = project_duplicate_error(course, slug)
    if error:
        return None, error

    return slug, None


def project_create_attrs(course, project_data):
    name = project_data.get("name")
    submission_due_str = project_data.get("submission_due_date")
    peer_review_due_str = project_data.get("peer_review_due_date")
    if not name or not submission_due_str or not peer_review_due_str:
        error = (
            "name, submission_due_date, and "
            "peer_review_due_date are required"
        )
        return None, error

    instructions_url, error = project_create_instructions_url(project_data)
    if error:
        return None, error

    submission_due_date = parse_date(submission_due_str)
    if submission_due_date is None:
        return None, f"Invalid date format: {submission_due_str}"

    peer_review_due_date = parse_date(peer_review_due_str)
    if peer_review_due_date is None:
        return None, f"Invalid date format: {peer_review_due_str}"

    slug, error = project_create_slug(course, project_data, name)
    if error:
        return None, error

    attrs = {
        "title": name,
        "description": project_data.get("description", ""),
        "instructions_url": instructions_url,
        "submission_due_date": submission_due_date,
        "peer_review_due_date": peer_review_due_date,
        "state": ProjectState.CLOSED.value,
        "slug": slug,
    }
    return attrs, None


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
