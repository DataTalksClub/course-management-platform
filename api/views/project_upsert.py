from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from courses.models import Course, Project
from courses.models.project import ProjectState

from api.safety import (
    PatchFieldRules,
    apply_patch_fields,
    error_response,
    require_staff_token,
)
from api.utils import instructions_url_error, parse_date, parse_json_body
from api.views.project_serializers import project_to_dict


PROJECT_PATCH_FIELDS = {
    "title",
    "description",
    "submission_due_date",
    "peer_review_due_date",
    "instructions_url",
    "state",
    "learning_in_public_cap_project",
    "learning_in_public_cap_review",
    "number_of_peers_to_evaluate",
    "points_for_peer_review",
    "time_spent_project_field",
    "problems_comments_field",
    "faq_contribution_field",
}

VALID_PROJECT_STATES = set()
for project_state in ProjectState:
    VALID_PROJECT_STATES.add(project_state.value)

PROJECT_PATCH_RULES = PatchFieldRules(
    PROJECT_PATCH_FIELDS,
    VALID_PROJECT_STATES,
    "invalid_project_state",
    {"submission_due_date", "peer_review_due_date"},
)

PROJECT_UPSERT_REQUIRED_DATES = (
    "submission_due_date",
    "peer_review_due_date",
)


def project_upsert_title(data):
    name = data.get("name")
    return data.get("title", name)


def project_upsert_missing_create_fields(data):
    title = project_upsert_title(data)
    missing_dates = []
    for field in PROJECT_UPSERT_REQUIRED_DATES:
        if not data.get(field):
            missing_dates.append(field)
    missing_title = not title
    has_missing_dates = bool(missing_dates)
    if missing_title:
        return True
    return has_missing_dates


def project_upsert_instructions_error(data):
    if "instructions_url" not in data:
        return None

    instructions_url = data.get("instructions_url")
    error = instructions_url_error(instructions_url)
    if not error:
        return None

    return error_response(
        error,
        "invalid_instructions_url",
        details={"field": "instructions_url"},
    )


def project_upsert_date_error(data):
    for field in PROJECT_UPSERT_REQUIRED_DATES:
        if field in data and parse_date(data[field]) is None:
            return error_response(
                f"Invalid date format for {field}",
                "invalid_date_format",
                details={"field": field},
            )
    return None


def project_upsert_state_error(data):
    if "state" not in data or data["state"] in VALID_PROJECT_STATES:
        return None

    valid_states = sorted(VALID_PROJECT_STATES)
    return error_response(
        f"Invalid state. Must be one of: {valid_states}",
        "invalid_project_state",
        details={"valid_states": valid_states},
    )


def project_upsert_validation_error(data, created):
    if created and project_upsert_missing_create_fields(data):
        return error_response(
            "title/name, submission_due_date, and peer_review_due_date are required",
            "missing_required_fields",
        )

    instructions_error = project_upsert_instructions_error(data)
    if instructions_error:
        return instructions_error

    date_error = project_upsert_date_error(data)
    if date_error:
        return date_error

    state_error = project_upsert_state_error(data)
    if state_error:
        return state_error

    return None


def project_by_slug(course, project_slug):
    project = Project.objects.filter(
        course=course,
        slug=project_slug,
    ).first()
    return project, project is None


def create_project_from_upsert(course, project_slug, data):
    title = project_upsert_title(data)
    description = data.get("description", "")
    instructions_url = data.get("instructions_url")
    submission_due_date = parse_date(data["submission_due_date"])
    peer_review_due_date = parse_date(data["peer_review_due_date"])

    return Project.objects.create(
        course=course,
        slug=project_slug,
        title=title,
        description=description,
        instructions_url=instructions_url,
        submission_due_date=submission_due_date,
        peer_review_due_date=peer_review_due_date,
        state=ProjectState.CLOSED.value,
    )


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


def upsert_project_by_slug(request, course_slug, project_slug):
    course = get_object_or_404(Course, slug=course_slug)
    data, err = parse_json_body(request)
    if err:
        return err

    project, created = project_by_slug(course, project_slug)
    error = project_upsert_validation_error(data, created)
    if error:
        return error

    if created:
        project = create_project_from_upsert(
            course, project_slug, data
        )

    return save_project_upsert(project, data, created)


def staff_upsert_project_by_slug(request, course_slug, project_slug):
    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    return upsert_project_by_slug(request, course_slug, project_slug)
