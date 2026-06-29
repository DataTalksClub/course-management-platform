from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils.text import slugify

from accounts.auth import token_required
from courses.models import Course, Project, PeerReview
from courses.models.project import ProjectState
from courses.projects import (
    ProjectActionStatus,
    assign_peer_reviews_for_project,
    score_project,
)

from api.crud import (
    bulk_create_response,
    detail_response,
    get_course_child_or_404,
)
from api.safety import (
    apply_patch_fields,
    error_response,
    require_staff_token,
)
from api.utils import (
    instructions_url_error,
    parse_date,
    parse_json_body,
    require_methods,
)


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
        "instructions_url": proj.instructions_url,
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


def _project_action_base(project, status, message):
    project.refresh_from_db()
    return {
        "status": status.name,
        "message": message,
        "project_id": project.id,
        "project_slug": project.slug,
        "state": project.state,
    }


def _project_assign_reviews_response(project):
    before_count = PeerReview.objects.filter(
        submission_under_evaluation__project=project,
    ).count()
    status, message = assign_peer_reviews_for_project(project)
    after_count = PeerReview.objects.filter(
        submission_under_evaluation__project=project,
    ).count()
    data = _project_action_base(project, status, message)
    data.update(
        {
            "peer_reviews_count": after_count,
            "assigned_peer_reviews_count": (
                after_count - before_count
                if status == ProjectActionStatus.OK
                else 0
            ),
        }
    )
    return JsonResponse(
        data,
        status=200 if status == ProjectActionStatus.OK else 400,
    )


def _project_score_response(project):
    scorable_submissions_count = (
        PeerReview.objects.filter(
            submission_under_evaluation__project=project,
        )
        .values("submission_under_evaluation")
        .distinct()
        .count()
    )
    status, message = score_project(project)
    submissions = project.projectsubmission_set.all()
    data = _project_action_base(project, status, message)
    data.update(
        {
            "submissions_count": submissions.count(),
            "scored_submissions_count": (
                scorable_submissions_count
                if status == ProjectActionStatus.OK
                else 0
            ),
            "passed_submissions_count": (
                submissions.filter(passed=True).count()
                if status == ProjectActionStatus.OK
                else 0
            ),
        }
    )
    return JsonResponse(
        data,
        status=200 if status == ProjectActionStatus.OK else 400,
    )


def _project_required_fields(proj_data):
    name = proj_data.get("name")
    submission_due_str = proj_data.get("submission_due_date")
    peer_review_due_str = proj_data.get("peer_review_due_date")
    return name, submission_due_str, peer_review_due_str


def _missing_project_required_fields(
    name,
    submission_due_str,
    peer_review_due_str,
):
    if name and submission_due_str and peer_review_due_str:
        return None
    return (
        "name, submission_due_date, and peer_review_due_date are required"
    )


def _project_instructions_url_error(proj_data):
    instructions_url = proj_data.get("instructions_url")
    if instructions_url:
        return instructions_url_error(instructions_url)
    return None


def _parse_project_due_dates(submission_due_str, peer_review_due_str):
    submission_due_date = parse_date(submission_due_str)
    if submission_due_date is None:
        return None, None, f"Invalid date format: {submission_due_str}"

    peer_review_due_date = parse_date(peer_review_due_str)
    if peer_review_due_date is None:
        return None, None, f"Invalid date format: {peer_review_due_str}"

    return submission_due_date, peer_review_due_date, None


def _project_slug(proj_data, name):
    return proj_data.get("slug") or slugify(name)


def _project_duplicate_error(course, slug):
    if Project.objects.filter(course=course, slug=slug).exists():
        return f"Project with slug '{slug}' already exists"
    return None


def _project_create_defaults(
    proj_data,
    name,
    instructions_url,
    submission_due_date,
    peer_review_due_date,
):
    return {
        "title": name,
        "description": proj_data.get("description", ""),
        "instructions_url": instructions_url,
        "submission_due_date": submission_due_date,
        "peer_review_due_date": peer_review_due_date,
        "state": ProjectState.CLOSED.value,
    }


def _create_project(course, proj_data):
    """Create a single project. Returns (dict, None) or (None, error_str)."""
    name, submission_due_str, peer_review_due_str = _project_required_fields(
        proj_data
    )
    if error := _missing_project_required_fields(
        name, submission_due_str, peer_review_due_str
    ):
        return None, error

    instructions_url = proj_data.get("instructions_url")
    if error := _project_instructions_url_error(proj_data):
        return None, error

    submission_due_date, peer_review_due_date, error = (
        _parse_project_due_dates(submission_due_str, peer_review_due_str)
    )
    if error:
        return None, error

    slug = _project_slug(proj_data, name)
    if error := _project_duplicate_error(course, slug):
        return None, error

    project = Project.objects.create(
        course=course,
        slug=slug,
        **_project_create_defaults(
            proj_data,
            name,
            instructions_url,
            submission_due_date,
            peer_review_due_date,
        ),
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
        return JsonResponse(
            {
                "projects": [_project_to_dict(p) for p in projects],
            }
        )

    # POST
    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    data, err = parse_json_body(request)
    if err:
        return err

    return bulk_create_response(
        data,
        lambda item: _create_project(course, item),
    )


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

VALID_PROJECT_STATES = {s.value for s in ProjectState}


def _apply_project_data(project, data):
    title = data.get("title", data.get("name"))
    if title is not None:
        project.title = title

    if "description" in data:
        project.description = data["description"]

    if "instructions_url" in data:
        error = instructions_url_error(data["instructions_url"])
        if error:
            return error_response(
                error,
                "invalid_instructions_url",
                details={"field": "instructions_url"},
            )
        project.instructions_url = data["instructions_url"]

    # The remaining scalar/date fields share the generic PATCH applier.
    # title / description / instructions_url are handled above, so exclude
    # them; everything else in PROJECT_PATCH_FIELDS flows through.
    handled = {"title", "name", "description", "instructions_url"}
    patch_data = {
        k: v
        for k, v in data.items()
        if k in PROJECT_PATCH_FIELDS and k not in handled
    }
    return apply_patch_fields(
        project,
        patch_data,
        allowed_fields=PROJECT_PATCH_FIELDS,
        valid_states=VALID_PROJECT_STATES,
        invalid_state_code="invalid_project_state",
        date_fields={"submission_due_date", "peer_review_due_date"},
    )


PROJECT_UPSERT_REQUIRED_DATES = (
    "submission_due_date",
    "peer_review_due_date",
)


def _project_upsert_title(data):
    return data.get("title", data.get("name"))


def _project_upsert_missing_create_fields(data):
    title = _project_upsert_title(data)
    missing_dates = [
        field
        for field in PROJECT_UPSERT_REQUIRED_DATES
        if not data.get(field)
    ]
    return not title or bool(missing_dates)


def _project_upsert_instructions_error(data):
    if "instructions_url" not in data:
        return None

    error = instructions_url_error(data.get("instructions_url"))
    if not error:
        return None

    return error_response(
        error,
        "invalid_instructions_url",
        details={"field": "instructions_url"},
    )


def _project_upsert_date_error(data):
    for field in PROJECT_UPSERT_REQUIRED_DATES:
        if field in data and parse_date(data[field]) is None:
            return error_response(
                f"Invalid date format for {field}",
                "invalid_date_format",
                details={"field": field},
            )
    return None


def _project_upsert_state_error(data):
    if "state" not in data or data["state"] in VALID_PROJECT_STATES:
        return None

    return error_response(
        f"Invalid state. Must be one of: {sorted(VALID_PROJECT_STATES)}",
        "invalid_project_state",
        details={"valid_states": sorted(VALID_PROJECT_STATES)},
    )


def _project_upsert_validation_error(data, created):
    if created and _project_upsert_missing_create_fields(data):
        return error_response(
            "title/name, submission_due_date, and peer_review_due_date are required",
            "missing_required_fields",
        )

    return (
        _project_upsert_instructions_error(data)
        or _project_upsert_date_error(data)
        or _project_upsert_state_error(data)
    )


def _project_by_slug(course, project_slug):
    project = Project.objects.filter(
        course=course,
        slug=project_slug,
    ).first()
    return project, project is None


def _create_project_from_upsert(course, project_slug, data):
    return Project.objects.create(
        course=course,
        slug=project_slug,
        title=_project_upsert_title(data),
        description=data.get("description", ""),
        instructions_url=data.get("instructions_url"),
        submission_due_date=parse_date(data["submission_due_date"]),
        peer_review_due_date=parse_date(data["peer_review_due_date"]),
        state=ProjectState.CLOSED.value,
    )


def _save_project_upsert(project, data, created):
    error = _apply_project_data(project, data)
    if error:
        return error

    project.save()
    return JsonResponse(
        _project_to_dict(project), status=201 if created else 200
    )


def _upsert_project_by_slug(request, course_slug, project_slug):
    course = get_object_or_404(Course, slug=course_slug)
    data, err = parse_json_body(request)
    if err:
        return err

    project, created = _project_by_slug(course, project_slug)
    error = _project_upsert_validation_error(data, created)
    if error:
        return error

    if created:
        project = _create_project_from_upsert(
            course, project_slug, data
        )

    return _save_project_upsert(project, data, created)


def _project_detail_response(
    request,
    course_slug,
    *,
    project_id=None,
    project_slug=None,
):
    course = get_object_or_404(Course, slug=course_slug)
    project = get_course_child_or_404(
        Project,
        course,
        object_id=project_id,
        slug=project_slug,
    )
    return detail_response(
        request,
        project,
        to_dict=_project_to_dict,
        allowed_fields=PROJECT_PATCH_FIELDS,
        valid_states=VALID_PROJECT_STATES,
        invalid_state_code="invalid_project_state",
        date_fields={"submission_due_date", "peer_review_due_date"},
        closed_state=ProjectState.CLOSED.value,
        related_queryset=project.projectsubmission_set.all(),
        related_name="submissions",
        noun="project",
    )


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
        staff_error = require_staff_token(request)
        if staff_error:
            return staff_error

        return _upsert_project_by_slug(
            request, course_slug, project_slug
        )

    return _project_detail_response(
        request, course_slug, project_slug=project_slug
    )


@token_required
@csrf_exempt
@require_methods("POST")
def project_assign_reviews_view(request, course_slug, project_id):
    """
    POST /api/courses/<slug>/projects/<id>/assign-reviews/ - Assign reviews.
    """
    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    course = get_object_or_404(Course, slug=course_slug)
    project = get_course_child_or_404(
        Project,
        course,
        object_id=project_id,
    )
    return _project_assign_reviews_response(project)


@token_required
@csrf_exempt
@require_methods("POST")
def project_assign_reviews_by_slug_view(
    request, course_slug, project_slug
):
    """
    POST /api/courses/<slug>/projects/by-slug/<slug>/assign-reviews/ - Assign reviews.
    """
    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    course = get_object_or_404(Course, slug=course_slug)
    project = get_course_child_or_404(
        Project,
        course,
        slug=project_slug,
    )
    return _project_assign_reviews_response(project)


@token_required
@csrf_exempt
@require_methods("POST")
def project_score_view(request, course_slug, project_id):
    """
    POST /api/courses/<slug>/projects/<id>/score/ - Score project.
    """
    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    course = get_object_or_404(Course, slug=course_slug)
    project = get_course_child_or_404(
        Project,
        course,
        object_id=project_id,
    )
    return _project_score_response(project)


@token_required
@csrf_exempt
@require_methods("POST")
def project_score_by_slug_view(request, course_slug, project_slug):
    """
    POST /api/courses/<slug>/projects/by-slug/<slug>/score/ - Score project.
    """
    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    course = get_object_or_404(Course, slug=course_slug)
    project = get_course_child_or_404(
        Project,
        course,
        slug=project_slug,
    )
    return _project_score_response(project)
