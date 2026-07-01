from django.views.decorators.csrf import csrf_exempt

from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_date

from accounts.auth import token_required
from courses.models import Course

from api.safety import error_response, require_staff_token
from api.utils import parse_json_body
from api.utils import require_methods


COURSE_PATCH_FIELDS = {
    "title",
    "description",
    "start_date",
    "end_date",
    "registration_url",
    "github_repo_url",
    "social_media_hashtag",
    "faq_document_url",
    "min_projects_to_pass",
    "homework_problems_comments_field",
    "project_passing_score",
    "finished",
    "visible",
}

COURSE_DATE_FIELDS = {"start_date", "end_date"}


def _date_to_iso(value):
    if value is None:
        return None
    return value.isoformat()


def _normalize_course_data(data):
    result = data.copy()

    for field in COURSE_DATE_FIELDS:
        if field not in result:
            continue

        value = result[field]
        if value in ("", None):
            result[field] = None
            continue

        parsed = parse_date(value)
        if parsed is None:
            return None, error_response(
                f"{field} must use YYYY-MM-DD format",
                "invalid_date",
                details={"field": field},
            )

        result[field] = parsed

    return result, None


def _validation_error_response(exc):
    if hasattr(exc, "message_dict"):
        details = exc.message_dict
    else:
        details = {"errors": exc.messages}

    return error_response(
        "Course validation failed",
        "validation_error",
        details=details,
    )


def _course_to_dict(course):
    return {
        "slug": course.slug,
        "title": course.title,
        "description": course.description,
        "start_date": _date_to_iso(course.start_date),
        "end_date": _date_to_iso(course.end_date),
        "registration_url": course.registration_url,
        "github_repo_url": course.github_repo_url,
        "finished": course.finished,
        "visible": course.visible,
        "social_media_hashtag": course.social_media_hashtag,
        "faq_document_url": course.faq_document_url,
        "min_projects_to_pass": course.min_projects_to_pass,
        "homework_problems_comments_field": (
            course.homework_problems_comments_field
        ),
        "project_passing_score": course.project_passing_score,
    }


def _course_summary_to_dict(course):
    result = _course_to_dict(course)
    hidden_fields = (
        "social_media_hashtag",
        "faq_document_url",
        "min_projects_to_pass",
        "homework_problems_comments_field",
        "project_passing_score",
    )
    for field in hidden_fields:
        result.pop(field)
    return result


def _course_homework_to_dict(homework):
    return {
        "id": homework.id,
        "slug": homework.slug,
        "title": homework.title,
        "instructions_url": homework.instructions_url,
        "due_date": homework.due_date.isoformat(),
        "state": homework.state,
    }


def _course_project_to_dict(project):
    return {
        "id": project.id,
        "slug": project.slug,
        "title": project.title,
        "instructions_url": project.instructions_url,
        "submission_due_date": project.submission_due_date.isoformat(),
        "peer_review_due_date": project.peer_review_due_date.isoformat(),
        "state": project.state,
    }


def _course_detail_to_dict(course):
    result = _course_to_dict(course)
    homeworks = course.homework_set.all().order_by("id")
    homework_records = []
    for homework in homeworks:
        homework_record = _course_homework_to_dict(homework)
        homework_records.append(homework_record)

    projects = course.project_set.all().order_by("id")
    project_records = []
    for project in projects:
        project_record = _course_project_to_dict(project)
        project_records.append(project_record)

    result.update(
        {
            "homeworks": homework_records,
            "projects": project_records,
        }
    )
    return result


def _courses_list_response():
    courses = Course.objects.all().order_by("id")
    course_records = []
    for course in courses:
        course_record = _course_summary_to_dict(course)
        course_records.append(course_record)

    payload = {
        "courses": course_records,
    }
    response = JsonResponse(payload)
    return response


def _missing_course_create_fields(data):
    missing_fields = []
    required_fields = ("title", "slug")
    for field in required_fields:
        if not data.get(field):
            missing_fields.append(field)
    return missing_fields


def _course_from_create_data(data):
    slug = data.get("slug")
    title = data.get("title")
    description = data.get("description", "")
    start_date = data.get("start_date")
    end_date = data.get("end_date")
    registration_url = data.get("registration_url", "")
    github_repo_url = data.get("github_repo_url", "")
    social_media_hashtag = data.get("social_media_hashtag", "")
    faq_document_url = data.get("faq_document_url", "")
    min_projects_to_pass = data.get("min_projects_to_pass", 1)
    homework_problems_comments_field = data.get(
        "homework_problems_comments_field", False
    )
    project_passing_score = data.get("project_passing_score", 0)
    finished = data.get("finished", False)
    visible = data.get("visible", True)

    course = Course(
        slug=slug,
        title=title,
        description=description,
        start_date=start_date,
        end_date=end_date,
        registration_url=registration_url,
        github_repo_url=github_repo_url,
        social_media_hashtag=social_media_hashtag,
        faq_document_url=faq_document_url,
        min_projects_to_pass=min_projects_to_pass,
        homework_problems_comments_field=homework_problems_comments_field,
        project_passing_score=project_passing_score,
        finished=finished,
        visible=visible,
    )
    return course


def _course_create_data_from_request(request):
    data, err = parse_json_body(request)
    if err:
        return None, err

    data, err = _normalize_course_data(data)
    if err:
        return None, err

    return data, None


def _missing_course_create_fields_response(data):
    if not _missing_course_create_fields(data):
        return None

    return error_response(
        "title and slug are required",
        "missing_required_fields",
    )


def _duplicate_course_slug_response(data):
    slug = data.get("slug")
    if not Course.objects.filter(slug=slug).exists():
        return None

    return error_response(
        f"Course with slug '{slug}' already exists",
        "course_slug_exists",
        details={"slug": slug},
    )


def _course_create_validation_error(course):
    try:
        course.full_clean()
    except ValidationError as exc:
        return _validation_error_response(exc)

    return None


def _validated_course_from_create_data(data):
    err = _missing_course_create_fields_response(data)
    if err:
        return None, err

    err = _duplicate_course_slug_response(data)
    if err:
        return None, err

    course = _course_from_create_data(data)
    err = _course_create_validation_error(course)
    if err:
        return None, err

    return course, None


def _create_course_response(request):
    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    data, err = _course_create_data_from_request(request)
    if err:
        return err

    course, err = _validated_course_from_create_data(data)
    if err:
        return err

    course.save()
    course_data = _course_to_dict(course)
    response = JsonResponse(course_data, status=201)
    return response


@token_required
@csrf_exempt
@require_methods("GET", "POST")
def courses_list_view(request):
    """
    GET /api/courses/ - List all courses.
    POST /api/courses/ - Create a course.
    """
    if request.method == "GET":
        return _courses_list_response()

    return _create_course_response(request)


def _invalid_course_patch_field(data):
    for field in data:
        if field not in COURSE_PATCH_FIELDS:
            return field
    return None


def _invalid_course_patch_field_response(data):
    invalid_field = _invalid_course_patch_field(data)
    if invalid_field is None:
        return None

    return error_response(
        f"Cannot update field: {invalid_field}",
        "invalid_field",
        details={"field": invalid_field},
    )


def _course_patch_data_from_request(request):
    data, err = parse_json_body(request)
    if err:
        return None, err

    err = _invalid_course_patch_field_response(data)
    if err:
        return None, err

    return _normalize_course_data(data)


def _apply_course_patch_data(course, data):
    for field, value in data.items():
        setattr(course, field, value)


def _course_patch_validation_error(course):
    try:
        course.full_clean()
    except ValidationError as exc:
        return _validation_error_response(exc)

    return None


def _patch_course_response(request, course):
    staff_error = require_staff_token(request)
    if staff_error:
        return staff_error

    data, err = _course_patch_data_from_request(request)
    if err:
        return err

    _apply_course_patch_data(course, data)
    err = _course_patch_validation_error(course)
    if err:
        return err

    course.save()
    course_data = _course_to_dict(course)
    response = JsonResponse(course_data)
    return response


@token_required
@csrf_exempt
@require_methods("GET", "PATCH")
def course_detail_view(request, course_slug):
    """
    GET /api/courses/<slug>/ - Course details.
    PATCH /api/courses/<slug>/ - Update course.
    """
    course = get_object_or_404(Course, slug=course_slug)

    if request.method == "PATCH":
        return _patch_course_response(request, course)

    course_data = _course_detail_to_dict(course)
    response = JsonResponse(course_data)
    return response
