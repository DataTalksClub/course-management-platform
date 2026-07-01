import logging
from time import time

from django.core.cache import cache
from django.db.models import Sum

from courses.models import (
    Enrollment,
    ProjectSubmission,
    Submission,
)


logger = logging.getLogger(__name__)


def _scores_by_enrollment(submissions):
    total_score_annotation = Sum("total_score")
    aggregated_scores = submissions.values("enrollment").annotate(
        total_score=total_score_annotation
    )
    scores_by_enrollment = {}
    for score in aggregated_scores:
        enrollment_id = score["enrollment"]
        scores_by_enrollment[enrollment_id] = score["total_score"]
    return scores_by_enrollment


def _enrollment_leaderboard_sort_key(enrollment):
    total_score = enrollment.total_score or 0
    return -total_score, enrollment.id


def _rank_enrollments(enrollments):
    enrollments = sorted(
        enrollments,
        key=_enrollment_leaderboard_sort_key,
    )
    for rank, enrollment in enumerate(enrollments, 1):
        enrollment.position_on_leaderboard = rank
    return enrollments


def _update_enrollment_totals(course):
    homework_submissions = Submission.objects.filter(homework__course=course)
    homework_scores = _scores_by_enrollment(homework_submissions)
    project_submissions = ProjectSubmission.objects.filter(
        project__course=course,
        volunteer_review_only=False,
    )
    project_scores = _scores_by_enrollment(project_submissions)
    enrollment_queryset = Enrollment.objects.filter(course=course)
    enrollments = list(enrollment_queryset)

    for enrollment in enrollments:
        enrollment.total_score = (
            homework_scores.get(enrollment.id, 0)
            + project_scores.get(enrollment.id, 0)
        )

    enrollments = _rank_enrollments(enrollments)

    Enrollment.objects.bulk_update(
        enrollments,
        ["total_score", "position_on_leaderboard"],
    )


def _invalidate_leaderboard_caches(course):
    cache.delete(f"leaderboard:{course.id}")
    cache.delete(f"leaderboard_data:{course.id}")
    cache.delete(f"leaderboard_yaml:{course.id}")
    version_key = f"leaderboard_cache_version:{course.id}"
    cache.set(version_key, cache.get(version_key, 1) + 1, None)
    logger.info(f"Invalidated cache for leaderboard of course {course.id}")


def update_leaderboard(course):
    started_at = time()
    logger.info(f"Updating leaderboard for course {course.id}")
    _update_enrollment_totals(course)
    _invalidate_leaderboard_caches(course)
    duration = time() - started_at
    logger.info(f"Updated leaderboard in {duration:.2f} seconds")
