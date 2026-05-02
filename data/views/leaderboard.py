"""
Public leaderboard data API view.

Returns the full leaderboard with per-homework and per-project score breakdowns.
Cached and invalidated when the leaderboard is recalculated.
"""

import logging

import yaml

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Prefetch
from django.db.models.functions import Coalesce
from django.db.models import Value

from courses.models import (
    Course,
    Enrollment,
    Submission,
    ProjectSubmission,
)
from courses.models.homework import HomeworkState
from courses.models.project import ProjectState

logger = logging.getLogger(__name__)

LEADERBOARD_DATA_CACHE_TTL = 86400  # 24 hours; also invalidated by update_leaderboard()
LEADERBOARD_YAML_CACHE_TTL = LEADERBOARD_DATA_CACHE_TTL
LEADERBOARD_DATA_PAGE_SIZE = 100


try:
    YamlDumper = yaml.CSafeDumper
except AttributeError:
    YamlDumper = yaml.SafeDumper


def _get_positive_int(value, default, maximum=None):
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default

    if result < 1:
        return default
    if maximum is not None:
        return min(result, maximum)
    return result


def _get_cache_version(course):
    version_key = f"leaderboard_cache_version:{course.id}"
    return cache.get(version_key, 1)


def _leaderboard_yaml_page_url(course, page_number):
    url = reverse(
        "api_course_leaderboard",
        kwargs={"course_slug": course.slug},
    )
    return f"{url}?page={page_number}"


def _build_leaderboard_data(course, page_number):
    """Build the full leaderboard JSON structure with score breakdowns."""
    enrollments = (
        Enrollment.objects.filter(course=course)
        .select_related("student")
        .prefetch_related(
            Prefetch(
                "submission_set",
                queryset=Submission.objects.filter(
                    homework__state=HomeworkState.SCORED.value,
                ).select_related("homework").order_by("homework__id"),
                to_attr="scored_submissions",
            ),
            Prefetch(
                "projectsubmission_set",
                queryset=ProjectSubmission.objects.filter(
                    project__state=ProjectState.COMPLETED.value,
                ).select_related("project").order_by("project__id"),
                to_attr="completed_project_submissions",
            ),
        )
        .order_by(
            Coalesce("position_on_leaderboard", Value(999999)),
            "id",
        )
    )

    paginator = Paginator(enrollments, LEADERBOARD_DATA_PAGE_SIZE)
    page_obj = paginator.get_page(page_number)

    results = []
    for enrollment in page_obj.object_list:
        hw_data = []
        for sub in enrollment.scored_submissions:
            hw_entry = {
                "homework": sub.homework.title,
                "homework_slug": sub.homework.slug,
                "total_score": sub.total_score,
                "questions_score": sub.questions_score,
                "faq_score": sub.faq_score,
                "learning_in_public_score": sub.learning_in_public_score,
            }
            if sub.homework_link:
                hw_entry["homework_link"] = sub.homework_link
            if sub.faq_contribution:
                hw_entry["faq_contribution"] = sub.faq_contribution
            if sub.learning_in_public_links:
                hw_entry["learning_in_public_links"] = sub.learning_in_public_links
            hw_data.append(hw_entry)

        proj_data = []
        for sub in enrollment.completed_project_submissions:
            proj_entry = {
                "project": sub.project.title,
                "project_slug": sub.project.slug,
                "total_score": sub.total_score,
                "project_score": sub.project_score,
                "peer_review_score": sub.peer_review_score,
                "project_learning_in_public_score": sub.project_learning_in_public_score,
                "peer_review_learning_in_public_score": sub.peer_review_learning_in_public_score,
                "project_faq_score": sub.project_faq_score,
                "passed": sub.passed,
            }
            if sub.github_link:
                proj_entry["github_link"] = sub.github_link
            if sub.faq_contribution:
                proj_entry["faq_contribution"] = sub.faq_contribution
            if sub.learning_in_public_links:
                proj_entry["learning_in_public_links"] = sub.learning_in_public_links
            proj_data.append(proj_entry)

        entry = {
            "position": enrollment.position_on_leaderboard,
            "display_name": enrollment.display_name,
            "total_score": enrollment.total_score,
        }
        if hw_data:
            entry["homeworks"] = hw_data
        if proj_data:
            entry["projects"] = proj_data

        results.append(entry)

    next_page_number = (
        page_obj.next_page_number() if page_obj.has_next() else None
    )
    previous_page_number = (
        page_obj.previous_page_number() if page_obj.has_previous() else None
    )

    return {
        "course": course.slug,
        "page": page_obj.number,
        "total_pages": paginator.num_pages,
        "total_entries": paginator.count,
        "has_next": page_obj.has_next(),
        "has_previous": page_obj.has_previous(),
        "next_page": (
            _leaderboard_yaml_page_url(course, next_page_number)
            if next_page_number
            else None
        ),
        "next_page_number": next_page_number,
        "previous_page": (
            _leaderboard_yaml_page_url(course, previous_page_number)
            if previous_page_number
            else None
        ),
        "previous_page_number": previous_page_number,
        "leaderboard": results,
    }


def leaderboard_data_view(request, course_slug: str):
    """Public endpoint returning the full leaderboard with score breakdowns."""
    course = get_object_or_404(Course, slug=course_slug)
    page = _get_positive_int(request.GET.get("page"), 1)
    cache_version = _get_cache_version(course)

    yaml_cache_key = (
        f"leaderboard_yaml:{course.id}:v{cache_version}:"
        f"page:{page}"
    )
    yaml_content = cache.get(yaml_cache_key)
    if yaml_content is not None:
        logger.info("Cache hit for leaderboard YAML of course %s", course.slug)
        return HttpResponse(yaml_content, content_type="text/plain; charset=utf-8")

    data_cache_key = (
        f"leaderboard_data:{course.id}:v{cache_version}:"
        f"page:{page}"
    )
    data = cache.get(data_cache_key)

    if data is None:
        logger.info("Cache miss for leaderboard data of course %s", course.slug)
        data = _build_leaderboard_data(course, page)
        cache.set(data_cache_key, data, LEADERBOARD_DATA_CACHE_TTL)
    else:
        logger.info("Cache hit for leaderboard data of course %s", course.slug)

    yaml_content = yaml.dump(
        data,
        Dumper=YamlDumper,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )
    cache.set(yaml_cache_key, yaml_content, LEADERBOARD_YAML_CACHE_TTL)

    return HttpResponse(yaml_content, content_type="text/plain; charset=utf-8")
