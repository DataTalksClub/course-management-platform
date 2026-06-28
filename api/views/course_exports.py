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


@require_GET
def course_criteria_yaml_view(request, course_slug: str):
    """Return project criteria for a course in YAML format (public endpoint, no auth required)."""
    course = get_object_or_404(Course, slug=course_slug)

    # Get all review criteria for the course
    review_criteria = ReviewCriteria.objects.filter(
        course=course
    ).order_by('id')

    # Convert criteria to a structured format for YAML export
    criteria_data = {
        'course': {
            'slug': course.slug,
            'title': course.title,
            'description': course.description,
        },
        'review_criteria': []
    }

    for criteria in review_criteria:
        criteria_dict = {
            'description': criteria.description,
            'type': dict(criteria.REVIEW_CRITERIA_TYPES)[criteria.review_criteria_type],
            'review_criteria_type': criteria.review_criteria_type,
            'options': criteria.options
        }
        criteria_data['review_criteria'].append(criteria_dict)

    # Convert to YAML
    yaml_content = yaml.dump(
        criteria_data,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False
    )

    # Return as HTTP response with content type that displays in browser
    response = HttpResponse(yaml_content, content_type='text/plain; charset=utf-8')

    return response
