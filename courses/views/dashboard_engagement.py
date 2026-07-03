from django.db.models import Count
from django.db.models.functions import TruncWeek

from courses.models.homework import Submission


def dashboard_engagement_trend(course):
    """Homework submissions per week over the course lifetime.

    Bar widths are relative to the busiest week so the trend shape is
    readable without a client-side charting library.
    """
    weekly = (
        Submission.objects
        .filter(homework__course=course, submitted_at__isnull=False)
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
