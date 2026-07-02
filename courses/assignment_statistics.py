import statistics

from .models.homework import (
    HomeworkState,
    HomeworkStatistics,
    Submission,
)
from .models.project import (
    ProjectState,
    ProjectStatistics,
    ProjectSubmission,
)


HOMEWORK_STAT_FIELDS = [
    "questions_score",
    "learning_in_public_score",
    "total_score",
    "time_spent_lectures",
    "time_spent_homework",
]

PROJECT_STAT_FIELDS = [
    "project_score",
    "project_learning_in_public_score",
    "peer_review_score",
    "peer_review_learning_in_public_score",
    "total_score",
    "time_spent",
]


def _field_values(submissions_data, field):
    values = []
    for submission in submissions_data:
        value = submission[field]
        if value is not None:
            values.append(value)
    return values


def _field_distribution(values):
    if len(values) < 3:
        return {
            "min": None,
            "max": None,
            "avg": None,
            "q1": None,
            "median": None,
            "q3": None,
        }

    quantiles = statistics.quantiles(values, n=4, method="inclusive")
    min_value = min(values)
    max_value = max(values)
    avg_value = statistics.mean(values)
    return {
        "min": min_value,
        "max": max_value,
        "avg": avg_value,
        "q1": quantiles[0],
        "median": quantiles[1],
        "q3": quantiles[2],
    }


def _calculate_field_distributions(submissions_data, fields):
    """Compute min/max/avg/quantiles per field from prefetched submission rows."""
    total_submissions = len(submissions_data)
    stats = {"total_submissions": total_submissions}

    for field in fields:
        field_values = _field_values(submissions_data, field)
        stats[field] = _field_distribution(field_values)

    return stats


def _persist_field_stats(stats, calculated_stats, fields):
    """Copy the computed distribution for each field onto a stats model instance."""
    stats.total_submissions = calculated_stats["total_submissions"]

    for field in fields:
        field_stats = calculated_stats[field]

        setattr(stats, f"min_{field}", field_stats["min"])
        setattr(stats, f"max_{field}", field_stats["max"])
        setattr(stats, f"avg_{field}", field_stats["avg"])
        setattr(stats, f"median_{field}", field_stats["median"])
        setattr(stats, f"q1_{field}", field_stats["q1"])
        setattr(stats, f"q3_{field}", field_stats["q3"])


def calculate_raw_homework_statistics(homework):
    # Single query to get all the fields we need, avoiding the N+1 problem
    submission_rows = Submission.objects.filter(homework=homework).values(
        *HOMEWORK_STAT_FIELDS
    )
    submissions_data = list(submission_rows)
    return _calculate_field_distributions(
        submissions_data, HOMEWORK_STAT_FIELDS
    )


def calculate_homework_statistics(homework, force=False):
    if homework.state != HomeworkState.SCORED.value:
        raise ValueError(
            f"Cannot calculate statistics for unscored homework {homework}"
        )

    stats, created = HomeworkStatistics.objects.get_or_create(
        homework=homework
    )

    if force or created:
        calculated_stats = calculate_raw_homework_statistics(homework)
        _persist_field_stats(
            stats, calculated_stats, HOMEWORK_STAT_FIELDS
        )
        stats.save()

    return stats


def calculate_raw_project_statistics(project):
    # Single query to get all the fields we need, avoiding the N+1 problem
    submission_rows = ProjectSubmission.objects.filter(
        project=project
    ).values(
        *PROJECT_STAT_FIELDS
    )
    submissions_data = list(submission_rows)
    return _calculate_field_distributions(
        submissions_data, PROJECT_STAT_FIELDS
    )


def calculate_project_statistics(project, force=False):
    if project.state != ProjectState.COMPLETED.value:
        raise ValueError(
            f"Cannot calculate statistics for uncompleted project {project}"
        )

    stats, created = ProjectStatistics.objects.get_or_create(
        project=project
    )

    if force or created:
        calculated_stats = calculate_raw_project_statistics(project)
        _persist_field_stats(
            stats, calculated_stats, PROJECT_STAT_FIELDS
        )
        stats.save()

    return stats
