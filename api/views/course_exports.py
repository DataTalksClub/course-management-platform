"""
Course-related data API views.

Provides views for exporting course criteria.
"""

import yaml

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from courses.models.course import Course
from courses.models.project import ReviewCriteria


def _review_criteria_export_data(criteria):
    return {
        'description': criteria.description,
        'type': dict(criteria.REVIEW_CRITERIA_TYPES)[
            criteria.review_criteria_type
        ],
        'review_criteria_type': criteria.review_criteria_type,
        'options': criteria.options
    }


def _course_criteria_export_data(course):
    review_criteria = []
    criteria_records = ReviewCriteria.objects.filter(course=course).order_by("id")
    for criteria in criteria_records:
        criteria_record = _review_criteria_export_data(criteria)
        review_criteria.append(criteria_record)

    return {
        "course": {
            "slug": course.slug,
            "title": course.title,
            "description": course.description,
        },
        "review_criteria": review_criteria,
    }


@require_GET
def course_criteria_yaml_view(request, course_slug: str):
    """Return project criteria for a course in YAML format."""
    course = get_object_or_404(Course, slug=course_slug)
    export_data = _course_criteria_export_data(course)
    criteria_yaml = yaml.safe_dump(
        export_data,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )
    response = HttpResponse(
        criteria_yaml,
        content_type="text/plain; charset=utf-8",
    )
    return response
