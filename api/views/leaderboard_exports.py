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
from django.views.decorators.http import require_GET

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


def _leaderboard_homework_entry(sub):
    """Score breakdown for one scored homework submission."""
    entry = {
        "homework": sub.homework.title,
        "homework_slug": sub.homework.slug,
        "total_score": sub.total_score,
        "questions_score": sub.questions_score,
        "faq_score": sub.faq_score,
        "learning_in_public_score": sub.learning_in_public_score,
    }
    if sub.homework_link:
        entry["homework_link"] = sub.homework_link
    if sub.faq_contribution_url:
        entry["faq_contribution_url"] = sub.faq_contribution_url
    if sub.learning_in_public_links:
        entry["learning_in_public_links"] = sub.learning_in_public_links
    return entry


def _leaderboard_project_entry(sub):
    """Score breakdown for one completed project submission."""
    entry = {
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
        entry["github_link"] = sub.github_link
    if sub.faq_contribution_url:
        entry["faq_contribution_url"] = sub.faq_contribution_url
    if sub.learning_in_public_links:
        entry["learning_in_public_links"] = sub.learning_in_public_links
    return entry


def _leaderboard_submission_prefetches():
    scored_submissions = (
        Submission.objects.filter(
            homework__state=HomeworkState.SCORED.value,
        )
        .select_related("homework")
        .order_by("homework__id")
    )
    completed_project_submissions = (
        ProjectSubmission.objects.filter(
            project__state=ProjectState.COMPLETED.value,
            volunteer_review_only=False,
        )
        .select_related("project")
        .order_by("project__id")
    )
    homework_prefetch = Prefetch(
        "submission_set",
        queryset=scored_submissions,
        to_attr="scored_submissions",
    )
    project_prefetch = Prefetch(
        "projectsubmission_set",
        queryset=completed_project_submissions,
        to_attr="completed_project_submissions",
    )
    return (
        homework_prefetch,
        project_prefetch,
    )


def _leaderboard_enrollments(course):
    prefetches = _leaderboard_submission_prefetches()
    empty_position = Value(999999)
    leaderboard_position = Coalesce(
        "position_on_leaderboard",
        empty_position,
    )
    return (
        Enrollment.objects.filter(
            course=course,
            display_on_leaderboard=True,
        )
        .select_related("student")
        .prefetch_related(*prefetches)
        .order_by(
            leaderboard_position,
            "id",
        )
    )


def _leaderboard_enrollment_entry(enrollment):
    hw_data = []
    scored_submissions = enrollment.scored_submissions
    for submission in scored_submissions:
        homework_entry = _leaderboard_homework_entry(submission)
        hw_data.append(homework_entry)

    proj_data = []
    completed_submissions = enrollment.completed_project_submissions
    for submission in completed_submissions:
        project_entry = _leaderboard_project_entry(submission)
        proj_data.append(project_entry)

    entry = {
        "position": enrollment.position_on_leaderboard,
        "display_name": enrollment.display_name,
        "total_score": enrollment.total_score,
    }
    if hw_data:
        entry["homeworks"] = hw_data
    if proj_data:
        entry["projects"] = proj_data
    return entry


def _leaderboard_page_links(course, page_obj):
    next_page_number = None
    if page_obj.has_next():
        next_page_number = page_obj.next_page_number()
    previous_page_number = None
    if page_obj.has_previous():
        previous_page_number = page_obj.previous_page_number()

    next_page = None
    if next_page_number:
        next_page = _leaderboard_yaml_page_url(course, next_page_number)
    previous_page = None
    if previous_page_number:
        previous_page = _leaderboard_yaml_page_url(course, previous_page_number)

    return {
        "next_page": next_page,
        "next_page_number": next_page_number,
        "previous_page": previous_page,
        "previous_page_number": previous_page_number,
    }


def _leaderboard_yaml_cache_key(course, cache_version, page):
    return (
        f"leaderboard_yaml:{course.id}:v{cache_version}:"
        f"page:{page}"
    )


def _leaderboard_data_cache_key(course, cache_version, page):
    return (
        f"leaderboard_data:{course.id}:v{cache_version}:"
        f"page:{page}"
    )


def _build_leaderboard_data(course, page_number):
    """Build the full leaderboard JSON structure with score breakdowns."""
    leaderboard_enrollments = _leaderboard_enrollments(course)
    paginator = Paginator(
        leaderboard_enrollments,
        LEADERBOARD_DATA_PAGE_SIZE,
    )
    page_obj = paginator.get_page(page_number)
    results = []
    enrollments = page_obj.object_list
    for enrollment in enrollments:
        enrollment_entry = _leaderboard_enrollment_entry(enrollment)
        results.append(enrollment_entry)

    has_next = page_obj.has_next()
    has_previous = page_obj.has_previous()
    page_links = _leaderboard_page_links(course, page_obj)
    return {
        "course": course.slug,
        "page": page_obj.number,
        "total_pages": paginator.num_pages,
        "total_entries": paginator.count,
        "has_next": has_next,
        "has_previous": has_previous,
        **page_links,
        "leaderboard": results,
    }


def _cached_leaderboard_data(course, page, cache_version):
    data_cache_key = _leaderboard_data_cache_key(
        course,
        cache_version,
        page,
    )
    data = cache.get(data_cache_key)
    if data is not None:
        logger.info("Cache hit for leaderboard data of course %s", course.slug)
        return data

    logger.info("Cache miss for leaderboard data of course %s", course.slug)
    data = _build_leaderboard_data(course, page)
    cache.set(data_cache_key, data, LEADERBOARD_DATA_CACHE_TTL)
    return data


def _leaderboard_yaml_content(data):
    yaml_content = yaml.safe_dump(
        data,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )
    return yaml_content


def _cached_leaderboard_yaml(course, page, cache_version):
    yaml_cache_key = _leaderboard_yaml_cache_key(
        course,
        cache_version,
        page,
    )
    yaml_content = cache.get(yaml_cache_key)
    if yaml_content is not None:
        logger.info("Cache hit for leaderboard YAML of course %s", course.slug)
        return yaml_content

    data = _cached_leaderboard_data(course, page, cache_version)
    yaml_content = _leaderboard_yaml_content(data)
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
