import logging
from time import time

from django.core.cache import cache
from django.db import connection

from courses.models.course import Enrollment
from courses.models.homework import Submission
from courses.models.project import (
    ProjectSubmission,
)


logger = logging.getLogger(__name__)


def _update_enrollment_totals(course):
    # Aggregate before joining: joining homework and project submissions directly
    # multiplies their rows. Rank every enrollment, including zero-score students,
    # using the existing deterministic tie-breaker. PostgreSQL and SQLite support
    # this CTE/window UPDATE; no model hydration or per-student CASE expressions.
    with connection.cursor() as cursor:
        cursor.execute(
            """
            WITH homework_scores AS (
                SELECT s.enrollment_id, SUM(s.total_score) AS score
                FROM courses_submission s
                JOIN courses_homework h ON h.id = s.homework_id
                WHERE h.course_id = %s GROUP BY s.enrollment_id
            ), project_scores AS (
                SELECT s.enrollment_id, SUM(s.total_score) AS score
                FROM courses_projectsubmission s
                JOIN courses_project p ON p.id = s.project_id
                WHERE p.course_id = %s AND NOT s.volunteer_review_only
                GROUP BY s.enrollment_id
            ), totals AS (
                SELECT e.id, COALESCE(h.score, 0) + COALESCE(p.score, 0) AS score
                FROM courses_enrollment e
                LEFT JOIN homework_scores h ON h.enrollment_id = e.id
                LEFT JOIN project_scores p ON p.enrollment_id = e.id
                WHERE e.course_id = %s
            ), ranked AS (
                SELECT id, score,
                       ROW_NUMBER() OVER (ORDER BY score DESC, id) AS position
                FROM totals
            )
            UPDATE courses_enrollment AS e
            SET total_score = ranked.score,
                position_on_leaderboard = ranked.position
            FROM ranked WHERE e.id = ranked.id
            """,
            [course.pk, course.pk, course.pk],
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
