import logging
from time import time

from courses.models.wrapped import WrappedStatistics

from .activity import wrapped_activity_context
from .persistence import (
    persist_wrapped_platform_statistics,
    persist_wrapped_user_statistics,
)


logger = logging.getLogger(__name__)


def wrapped_statistics_to_calculate(year, force):
    stats, created = WrappedStatistics.objects.get_or_create(year=year)
    if not force and not created:
        logger.info(
            f"Wrapped statistics for {year} already exist. Use force=True to recalculate."
        )
        return stats, False
    return stats, True


def calculate_wrapped_statistics_body(stats, year):
    logger.info(f"Calculating wrapped statistics for {year}...")
    start_time = time()

    activity = wrapped_activity_context(year)
    leaderboard_data = persist_wrapped_platform_statistics(
        stats,
        activity,
    )

    logger.info(
        "Platform statistics calculated. Now calculating individual user statistics..."
    )
    user_stats_objects = persist_wrapped_user_statistics(
        stats,
        activity,
        leaderboard_data,
    )

    log_wrapped_statistics_calculated(
        year,
        start_time,
        user_stats_objects,
    )


def log_wrapped_statistics_calculated(
    year,
    start_time,
    user_stats_objects,
):
    elapsed_time = time() - start_time
    logger.info(
        f"Wrapped statistics for {year} calculated successfully in {elapsed_time:.2f} seconds. "
        f"Processed {len(user_stats_objects)} users."
    )


def calculate_wrapped_statistics(year=2025, force=False):
    """
    Calculate and save wrapped statistics for a given year.
    This function pre-calculates all the statistics that would be needed
    for the wrapped page to avoid slow queries on page load.

    Args:
        year: The year to calculate statistics for (default: 2025)
        force: If True, recalculate even if statistics already exist

    Returns:
        WrappedStatistics object
    """
    stats, should_calculate = wrapped_statistics_to_calculate(year, force)
    if not should_calculate:
        return stats

    calculate_wrapped_statistics_body(stats, year)
    return stats
