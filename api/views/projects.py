import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils.text import slugify

from accounts.auth import token_required
from courses.models import Course, Project
from courses.models.project import ProjectState

from api.safety import (
    error_response,
    ensure_closed_for_delete,
    ensure_no_related_records_for_delete,
)
from api.utils import parse_date, parse_json_body, require_methods


def _project_delete_blockers(proj):
    blockers = []
    submissions_count = proj.projectsubmission_set.count()
    if proj.state != ProjectState.CLOSED.value:
        blockers.append("not_closed")
    if submissions_count > 0:
        blockers.append("has_submissions")
    return blockers


def _project_to_dict(proj):
    submissions_count = proj.projectsubmission_set.count()
    delete_blockers = _project_delete_blockers(proj)
    return {
        "id": proj.id,
        "slug": proj.slug,
        "title": proj.title,
        "description": proj.description,
        "submission_due_date": proj.submission_due_date.isoformat(),
        "peer_review_due_date": proj.peer_review_due_date.isoformat(),
        "state": proj.state,
        "learning_in_public_cap_project": proj.learning_in_public_cap_project,
        "learning_in_public_cap_review": proj.learning_in_public_cap_review,
        "number_of_peers_to_evaluate": proj.number_of_peers_to_evaluate,
        "points_for_peer_review": proj.points_for_peer_review,
        "time_spent_project_field": proj.time_spent_project_field,
        "problems_comments_field": proj.problems_comments_field,
        "faq_contribution_field": proj.faq_contribution_field,
        "submissions_count": submissions_count,
        "can_delete": not delete_blockers,
        "delete_blockers": delete_blockers,
    }


def _create_project(course, proj_data):
    """Create a single project. Returns (dict, None) or (None, error_str)."""
    name = proj_data.get("name")
    submission_due_str = proj_data.get("submission_due_date")
    peer_review_due_str = proj_data.get("peer_review_due_date")

    if not name or not submission_due_str or not peer_review_due_str:
        return None, "name, submission_due_date, and peer_review_due_date are required"

    submission_due_date = parse_date(submission_due_str)
    if submission_due_date is None:
        return None, f"Invalid date format: {submission_due_str}"

    peer_review_due_date = parse_date(peer_review_due_str)
    if peer_review_due_date is None:
        return None, f"Invalid date format: {peer_review_due_str}"

    slug = proj_data.get("slug") or slugify(name)

    if Project.objects.filter(course=course, slug=slug).exists():
        return None, f"Project with slug '{slug}' already exists"

    project = Project.objects.create(
        course=course,
        slug=slug,
        title=name,
        description=proj_data.get("description", ""),
        submission_due_date=submission_due_date,
        peer_review_due_date=peer_review_due_date,
        state=ProjectState.CLOSED.value,
    )

    return _project_to_dict(project), None


@token_required
@csrf_exempt
@require_methods("GET", "POST")
def projects_view(request, course_slug):
    """
    GET /api/courses/<slug>/projects/ - List projects.
    POST /api/courses/<slug>/projects/ - Create project(s), bulk supported.
    """
    course = get_object_or_404(Course, slug=course_slug)

    if request.method == "GET":
        projects = Project.objects.filter(course=course).order_by("id")
        return JsonResponse({
            "projects": [_project_to_dict(p) for p in projects],
        })

    # POST
    data, err = parse_json_body(request)
    if err:
        return err

    items = data if isinstance(data, list) else [data]

    created = []
    errors = []
    for item in items:
        proj_dict, error = _create_project(course, item)
        if error:
            errors.append({"name": item.get("name", "unknown"), "error": error})
        else:
            created.append(proj_dict)

    result = {"created": created}
    if errors:
        result["errors"] = errors

    status = 201 if created else 400
    return JsonResponse(result, status=status)


PROJECT_PATCH_FIELDS = {
    "title", "description", "submission_due_date", "peer_review_due_date",
    "state", "learning_in_public_cap_project", "learning_in_public_cap_review",
    "number_of_peers_to_evaluate", "points_for_peer_review",
    "time_spent_project_field", "problems_comments_field", "faq_contribution_field",
}

VALID_PROJECT_STATES = {s.value for s in ProjectState}


def _apply_project_data(project, data):
    title = data.get("title", data.get("name"))
    if title is not None:
        project.title = title

    if "description" in data:
        project.description = data["description"]

    for field in ("submission_due_date", "peer_review_due_date"):
        if field not in data:
            continue
        value = parse_date(data[field])
        if value is None:
            return error_response(
                f"Invalid date format for {field}",
                "invalid_date_format",
                details={"field": field},
            )
        setattr(project, field, value)

    for field in (
        "state",
        "learning_in_public_cap_project",
        "learning_in_public_cap_review",
        "number_of_peers_to_evaluate",
        "points_for_peer_review",
        "time_spent_project_field",
        "problems_comments_field",
        "faq_contribution_field",
    ):
        if field not in data:
            continue
        value = data[field]
        if field == "state" and value not in VALID_PROJECT_STATES:
            return error_response(
                f"Invalid state. Must be one of: {sorted(VALID_PROJECT_STATES)}",
                "invalid_project_state",
                details={"valid_states": sorted(VALID_PROJECT_STATES)},
            )
        setattr(project, field, value)

    return None


def _upsert_project_by_slug(request, course_slug, project_slug):
    course = get_object_or_404(Course, slug=course_slug)
    data, err = parse_json_body(request)
    if err:
        return err

    project = Project.objects.filter(
        course=course,
        slug=project_slug,
    ).first()
    created = project is None

    title = data.get("title", data.get("name"))
    required_dates = ("submission_due_date", "peer_review_due_date")
    if created and (not title or not all(data.get(f) for f in required_dates)):
        return error_response(
            "title/name, submission_due_date, and peer_review_due_date are required",
            "missing_required_fields",
        )

    for field in required_dates:
        if field in data and parse_date(data[field]) is None:
            return error_response(
                f"Invalid date format for {field}",
                "invalid_date_format",
                details={"field": field},
            )

    if "state" in data and data["state"] not in VALID_PROJECT_STATES:
        return error_response(
            f"Invalid state. Must be one of: {sorted(VALID_PROJECT_STATES)}",
            "invalid_project_state",
            details={"valid_states": sorted(VALID_PROJECT_STATES)},
        )

    if created:
        project = Project.objects.create(
            course=course,
            slug=project_slug,
            title=title,
            description=data.get("description", ""),
            submission_due_date=parse_date(data["submission_due_date"]),
            peer_review_due_date=parse_date(data["peer_review_due_date"]),
            state=ProjectState.CLOSED.value,
        )

    error = _apply_project_data(project, data)
    if error:
        return error

    project.save()
    return JsonResponse(_project_to_dict(project), status=201 if created else 200)


def _project_detail_response(
    request,
    course_slug,
    *,
    project_id=None,
    project_slug=None,
):
    course = get_object_or_404(Course, slug=course_slug)
    if project_id is not None:
        project = get_object_or_404(Project, course=course, id=project_id)
    else:
        project = get_object_or_404(Project, course=course, slug=project_slug)

    if request.method == "GET":
        return JsonResponse(_project_to_dict(project))

    if request.method == "DELETE":
        error_response_result = ensure_closed_for_delete(
            project, ProjectState.CLOSED.value, "project"
        )
        if error_response_result:
            return error_response_result

        error_response_result = ensure_no_related_records_for_delete(
            project.projectsubmission_set.all(), "submissions", "project"
        )
        if error_response_result:
            return error_response_result

        project.delete()
        return JsonResponse({"deleted": True})

    data, err = parse_json_body(request)
    if err:
        return err

    for field, value in data.items():
        if field not in PROJECT_PATCH_FIELDS:
            return error_response(
                f"Cannot update field: {field}",
                "invalid_field",
                details={"field": field},
            )

        if field == "state":
            if value not in VALID_PROJECT_STATES:
                return error_response(
                    f"Invalid state. Must be one of: {sorted(VALID_PROJECT_STATES)}",
                    "invalid_project_state",
                    details={"valid_states": sorted(VALID_PROJECT_STATES)},
                )

        if field in ("submission_due_date", "peer_review_due_date"):
            value = parse_date(value)
            if value is None:
                return error_response(
                    f"Invalid date format for {field}",
                    "invalid_date_format",
                    details={"field": field},
                )

        setattr(project, field, value)

    project.save()
    return JsonResponse(_project_to_dict(project))


@token_required
@csrf_exempt
@require_methods("GET", "PATCH", "DELETE")
def project_detail_view(request, course_slug, project_id):
    """
    GET /api/courses/<slug>/projects/<id>/ - Project detail.
    PATCH /api/courses/<slug>/projects/<id>/ - Update project.
    DELETE /api/courses/<slug>/projects/<id>/ - Delete project.
    """
    return _project_detail_response(
        request, course_slug, project_id=project_id
    )


@token_required
@csrf_exempt
@require_methods("GET", "PUT", "PATCH", "DELETE")
def project_detail_by_slug_view(request, course_slug, project_slug):
    """
    GET /api/courses/<slug>/projects/by-slug/<slug>/ - Project detail.
    PUT /api/courses/<slug>/projects/by-slug/<slug>/ - Upsert project.
    PATCH /api/courses/<slug>/projects/by-slug/<slug>/ - Update project.
    DELETE /api/courses/<slug>/projects/by-slug/<slug>/ - Delete project.
    """
    if request.method == "PUT":
        return _upsert_project_by_slug(request, course_slug, project_slug)

    return _project_detail_response(
        request, course_slug, project_slug=project_slug
    )
