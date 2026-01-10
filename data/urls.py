from django.urls import path

from . import views as data_views


urlpatterns = [
    # Health check (public, no auth required)
    path(
        "health/",
        data_views.health_view,
        name="health",
    ),

    # Course criteria (public, no auth required)
    path(
        "<slug:course_slug>/course-criteria.yaml",
        data_views.course_criteria_yaml_view,
        name="course_criteria_yaml",
    ),

    # Data API endpoints (require auth)
    path(
        "<slug:course_slug>/homework/<slug:homework_slug>",
        data_views.homework_data_view,
        name="data_homework",
    ),
    path(
        "<slug:course_slug>/project/<slug:project_slug>",
        data_views.project_data_view,
        name="data_project",
    ),
    path(
        "<slug:course_slug>/graduates",
        data_views.graduates_data_view,
        name="data_graduates",
    ),
    path(
        "<slug:course_slug>/update-certificate",
        data_views.update_enrollment_certificate_view,
        name="data_update_certificate",
    ),
    path(
        "<slug:course_slug>/content",
        data_views.course_content_view,
        name="data_content",
    ),
    path(
        "<slug:course_slug>/homework/<slug:homework_slug>/content",
        data_views.homework_content_view,
        name="data_homework_content",
    ),
]
