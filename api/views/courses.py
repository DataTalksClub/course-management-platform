from django.views.decorators.csrf import csrf_exempt

from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_date

from accounts.auth import token_required
from courses.models import Course

from api.safety import error_response
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
    for field in (
        "social_media_hashtag",
        "faq_document_url",
        "min_projects_to_pass",
        "homework_problems_comments_field",
        "project_passing_score",
    ):
        result.pop(field)
    return result


@token_required
@csrf_exempt
@require_methods("GET", "POST")
def courses_list_view(request):
    """
    GET /api/courses/ - List all courses.
    POST /api/courses/ - Create a course.
    """
    if request.method == "GET":
        courses = Course.objects.all().order_by("id")
        return JsonResponse({
            "courses": [_course_summary_to_dict(course) for course in courses],
        })

    data, err = parse_json_body(request)
    if err:
        return err

    data, err = _normalize_course_data(data)
    if err:
        return err

    title = data.get("title")
    slug = data.get("slug")
    if not title or not slug:
        return error_response(
            "title and slug are required",
            "missing_required_fields",
        )

    if Course.objects.filter(slug=slug).exists():
        return error_response(
            f"Course with slug '{slug}' already exists",
            "course_slug_exists",
            details={"slug": slug},
        )

    course = Course(
        slug=slug,
        title=title,
        description=data.get("description", ""),
        start_date=data.get("start_date"),
        end_date=data.get("end_date"),
        registration_url=data.get("registration_url", ""),
        github_repo_url=data.get("github_repo_url", ""),
        social_media_hashtag=data.get("social_media_hashtag", ""),
        faq_document_url=data.get("faq_document_url", ""),
        min_projects_to_pass=data.get("min_projects_to_pass", 1),
        homework_problems_comments_field=data.get(
            "homework_problems_comments_field", False
        ),
        project_passing_score=data.get("project_passing_score", 0),
        finished=data.get("finished", False),
        visible=data.get("visible", True),
    )
    try:
        course.full_clean()
    except ValidationError as exc:
        return _validation_error_response(exc)

    course.save()
    return JsonResponse(_course_to_dict(course), status=201)


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
        data, err = parse_json_body(request)
        if err:
            return err

        for field, value in data.items():
            if field not in COURSE_PATCH_FIELDS:
                return error_response(
                    f"Cannot update field: {field}",
                    "invalid_field",
                    details={"field": field},
                )

        data, err = _normalize_course_data(data)
        if err:
            return err

        for field, value in data.items():
            setattr(course, field, value)

        try:
            course.full_clean()
        except ValidationError as exc:
            return _validation_error_response(exc)

        course.save()
        return JsonResponse(_course_to_dict(course))

    homeworks = course.homework_set.all().order_by("id")
    projects = course.project_set.all().order_by("id")

    result = _course_to_dict(course)
    result.update({
        "homeworks": [
            {
                "id": hw.id,
                "slug": hw.slug,
                "title": hw.title,
                "instructions_url": hw.instructions_url,
                "due_date": hw.due_date.isoformat(),
                "state": hw.state,
            }
            for hw in homeworks
        ],
        "projects": [
            {
                "id": p.id,
                "slug": p.slug,
                "title": p.title,
                "instructions_url": p.instructions_url,
                "submission_due_date": p.submission_due_date.isoformat(),
                "peer_review_due_date": p.peer_review_due_date.isoformat(),
                "state": p.state,
            }
            for p in projects
        ],
    })
    return JsonResponse(result)
