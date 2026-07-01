from django.shortcuts import get_object_or_404

from courses.models.course import Course

from api.utils import parse_json_body
from api.views.project_upsert_persistence import (
    create_project_from_upsert,
    project_by_slug,
    save_project_upsert,
)
from api.views.project_upsert_validation import (
    project_upsert_validation_error,
)


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
