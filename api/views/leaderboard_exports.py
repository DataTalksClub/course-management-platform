"""
Public leaderboard data API view.

Returns the full leaderboard with per-homework and per-project score breakdowns.
Cached and invalidated when the leaderboard is recalculated.
"""

import logging

import yaml

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.core.cache import cache
from django.views.decorators.http import require_GET

from api.views.leaderboard_export_data import (
    build_leaderboard_data,
)
from courses.models.course import Course

logger = logging.getLogger(__name__)

LEADERBOARD_DATA_CACHE_TTL = 86400  # 24 hours; also invalidated by update_leaderboard()
LEADERBOARD_YAML_CACHE_TTL = LEADERBOARD_DATA_CACHE_TTL


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


def _cached_leaderboard_data(course, page, cache_version):
    data_cache_key = (
        f"leaderboard_data:{course.id}:v{cache_version}:"
        f"page:{page}"
    )
    data = cache.get(data_cache_key)
    if data is not None:
        logger.info("Cache hit for leaderboard data of course %s", course.slug)
        return data

    logger.info("Cache miss for leaderboard data of course %s", course.slug)
    data = build_leaderboard_data(course, page)
    cache.set(data_cache_key, data, LEADERBOARD_DATA_CACHE_TTL)
    return data


def _cached_leaderboard_yaml(course, page, cache_version):
    yaml_cache_key = (
        f"leaderboard_yaml:{course.id}:v{cache_version}:"
        f"page:{page}"
    )
    yaml_content = cache.get(yaml_cache_key)
    if yaml_content is not None:
        logger.info("Cache hit for leaderboard YAML of course %s", course.slug)
        return yaml_content

    data = _cached_leaderboard_data(course, page, cache_version)
    yaml_content = yaml.safe_dump(
        data,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )
    cache.set(yaml_cache_key, yaml_content, LEADERBOARD_YAML_CACHE_TTL)
    return yaml_content


@require_GET
def leaderboard_data_view(request, course_slug: str):
    """Public endpoint returning the full leaderboard with score breakdowns."""
    course = get_object_or_404(Course, slug=course_slug)
    page_value = request.GET.get("page")
    page = _get_positive_int(page_value, 1)
    cache_version = _get_cache_version(course)
    yaml_content = _cached_leaderboard_yaml(course, page, cache_version)
    response = HttpResponse(
        yaml_content,
        content_type="text/plain; charset=utf-8",
    )
    return response
