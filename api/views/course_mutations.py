from django.core.exceptions import ValidationError
from django.utils.dateparse import parse_date

from api.safety import error_response
from api.utils import parse_json_body
from courses.models import Course


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


def course_create_data_from_request(request):
    data, err = parse_json_body(request)
    if err:
        return None, err

    data, err = normalize_course_data(data)
    if err:
        return None, err

    return data, None


def validated_course_from_create_data(data):
    err = missing_course_create_fields_response(data)
    if err:
        return None, err

    err = duplicate_course_slug_response(data)
    if err:
        return None, err

    course = course_from_create_data(data)
    err = course_validation_error(course)
    if err:
        return None, err

    return course, None


def course_patch_data_from_request(request):
    data, err = parse_json_body(request)
    if err:
        return None, err

    err = invalid_course_patch_field_response(data)
    if err:
        return None, err

    return normalize_course_data(data)


def apply_course_patch_data(course, data):
    for field, value in data.items():
        setattr(course, field, value)


def course_validation_error(course):
    try:
        course.full_clean()
    except ValidationError as exc:
        return validation_error_response(exc)

    return None


def normalize_course_data(data):
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


def validation_error_response(exc):
    if hasattr(exc, "message_dict"):
        details = exc.message_dict
    else:
        details = {"errors": exc.messages}

    return error_response(
        "Course validation failed",
        "validation_error",
        details=details,
    )


def missing_course_create_fields(data):
    missing_fields = []
    required_fields = ("title", "slug")
    for field in required_fields:
        if not data.get(field):
            missing_fields.append(field)
    return missing_fields


def missing_course_create_fields_response(data):
    if not missing_course_create_fields(data):
        return None

    return error_response(
        "title and slug are required",
        "missing_required_fields",
    )


def duplicate_course_slug_response(data):
    slug = data.get("slug")
    if not Course.objects.filter(slug=slug).exists():
        return None

    return error_response(
        f"Course with slug '{slug}' already exists",
        "course_slug_exists",
        details={"slug": slug},
    )


def course_from_create_data(data):
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


def invalid_course_patch_field(data):
    for field in data:
        if field not in COURSE_PATCH_FIELDS:
            return field
    return None


def invalid_course_patch_field_response(data):
    invalid_field = invalid_course_patch_field(data)
    if invalid_field is None:
        return None

    return error_response(
        f"Cannot update field: {invalid_field}",
        "invalid_field",
        details={"field": invalid_field},
    )
