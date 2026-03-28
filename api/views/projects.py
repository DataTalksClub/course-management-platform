import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils.text import slugify

from accounts.auth import token_required
from courses.models import Course, Project
from courses.models.project import ProjectState

from api.utils import parse_date, parse_json_body, require_methods


def _project_to_dict(proj):
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


@token_required
@csrf_exempt
@require_methods("PATCH", "DELETE")
def project_detail_view(request, course_slug, project_id):
    """
    PATCH /api/courses/<slug>/projects/<id>/ - Update project.
    DELETE /api/courses/<slug>/projects/<id>/ - Delete project (closed only).
    """
    course = get_object_or_404(Course, slug=course_slug)
    project = get_object_or_404(Project, course=course, id=project_id)

    if request.method == "DELETE":
        if project.state != ProjectState.CLOSED.value:
            return JsonResponse(
                {"error": "Only closed projects can be deleted"},
                status=400,
            )
        project.delete()
        return JsonResponse({"deleted": True})

    # PATCH
    data, err = parse_json_body(request)
    if err:
        return err

    for field, value in data.items():
        if field not in PROJECT_PATCH_FIELDS:
            return JsonResponse(
                {"error": f"Cannot update field: {field}"},
                status=400,
            )

        if field == "state":
            if value not in VALID_PROJECT_STATES:
                return JsonResponse(
                    {"error": f"Invalid state. Must be one of: {sorted(VALID_PROJECT_STATES)}"},
                    status=400,
                )

        if field in ("submission_due_date", "peer_review_due_date"):
            value = parse_date(value)
            if value is None:
                return JsonResponse(
                    {"error": f"Invalid date format for {field}"},
                    status=400,
                )

        setattr(project, field, value)

    project.save()
    return JsonResponse(_project_to_dict(project))
