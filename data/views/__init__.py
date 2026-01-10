"""
Data API views for course management.

This module exports all views from the data app's view modules.
"""

from .homework import homework_data_view, homework_content_view
from .project import project_data_view
from .course import course_content_view, course_criteria_yaml_view
from .enrollment import graduates_data_view, update_enrollment_certificate_view
from .health import health_view

# Backwards compatible aliases
from .course import course_content_view as create_course_content_view

__all__ = [
    "homework_data_view",
    "homework_content_view",
    "project_data_view",
    "course_content_view",
    "course_criteria_yaml_view",
    "graduates_data_view",
    "update_enrollment_certificate_view",
    "create_course_content_view",
    "health_view",
]
