from collections import defaultdict
import datetime

from django.db.models import Count
from django.db.models.functions import TruncWeek

from courses.models.course import Course
from courses.models.homework import Submission


def dashboard_engagement_trend(course_or_submissions):
    """Homework submissions per week over the course lifetime.

    Bar widths are relative to the busiest week so the trend shape is
    readable without a client-side charting library. Consumes the same
    rows dashboard_homework_submissions() already fetched so we do not
    issue a second full scan of courses_submission.
    """
    if not isinstance(course_or_submissions, Course):
        week_counts = defaultdict(int)
        for submission in course_or_submissions:
            submitted_at = (
                submission[5]
                if isinstance(submission, tuple)
                else submission.get("submitted_at")
            )
            if submitted_at is None:
                continue
            monday_ordinal = (
                submitted_at.toordinal() - submitted_at.weekday()
            )
            week_counts[monday_ordinal] += 1

        if not week_counts:
            return []

        max_count = max(week_counts.values())
        return [
            {
                "label": datetime.date.fromordinal(
                    monday_ordinal
                ).strftime("%b %d, %Y"),
                "count": count,
                "bar_pct": round(count / max_count * 100, 1),
            }
            for monday_ordinal, count in sorted(week_counts.items())
        ]

    weekly = (
        Submission.objects
        .filter(
            homework__course=course_or_submissions,
            submitted_at__isnull=False,
        )
        .annotate(week=TruncWeek("submitted_at"))
        .values("week")
        .annotate(count=Count("id"))
        .order_by("week")
    )

    buckets = [
        {"week": row["week"], "count": row["count"]}
        for row in weekly
        if row["week"] is not None
    ]
    if not buckets:
        return []

    max_count = max(bucket["count"] for bucket in buckets)
    return [
        {
            "label": bucket["week"].strftime("%b %d, %Y"),
            "count": bucket["count"],
            "bar_pct": round(bucket["count"] / max_count * 100, 1),
        }
        for bucket in buckets
    ]
