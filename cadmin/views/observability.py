from django.shortcuts import render

from course_management.observability.cloudwatch_dashboard import (
    CloudWatchDashboardError,
    cloudwatch_dashboard_context,
    cloudwatch_dashboard_error_context,
    normalized_hours,
)

from .helpers import staff_required


@staff_required
def cloudwatch_dashboard(request):
    environment = request.GET.get("environment", "").strip() or None
    hours = normalized_hours(int_or_default(request.GET.get("hours"), 24))

    try:
        context = cloudwatch_dashboard_context(
            environment=environment,
            hours=hours,
        )
    except CloudWatchDashboardError as exc:
        context = cloudwatch_dashboard_error_context(
            environment=environment,
            hours=hours,
            error=str(exc),
        )

    return render(request, "cadmin/cloudwatch_dashboard.html", context)


def int_or_default(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
