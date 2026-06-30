"""
Course-related data API views.

Provides views for exporting course criteria.
"""

import yaml

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from courses.models import (
    Course,
    ReviewCriteria,
)


def _course_review_criteria(course):
    return ReviewCriteria.objects.filter(
        course=course
    ).order_by('id')


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
    criteria_records = _course_review_criteria(course)
    for criteria in criteria_records:
        criteria_record = _review_criteria_export_data(criteria)
        review_criteria.append(criteria_record)

    return {
        'course': {
            'slug': course.slug,
            'title': course.title,
            'description': course.description,
        },
        'review_criteria': review_criteria,
    }


def _course_criteria_yaml(course):
    export_data = _course_criteria_export_data(course)
    yaml_content = yaml.safe_dump(
        export_data,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False
    )
    return yaml_content


@require_GET
def course_criteria_yaml_view(request, course_slug: str):
    """Return project criteria for a course in YAML format."""
    course = get_object_or_404(Course, slug=course_slug)
    criteria_yaml = _course_criteria_yaml(course)
    response = HttpResponse(
        criteria_yaml,
        content_type='text/plain; charset=utf-8',
    )
    return response
