from dataclasses import dataclass
from datetime import UTC, timedelta
from math import floor

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
from django.conf import settings
from django.utils import timezone

from course_management.observability.cloudwatch import METRIC_NAME
from course_management.observability.events import observability_environment


DEFAULT_DASHBOARD_EVENTS = [
    (
        "registration.submitted",
        "Registrations",
        "Landing page registrations submitted.",
    ),
    (
        "enrollment.created",
        "Enrollments",
        "Course enrollments created.",
    ),
    (
        "homework.submitted",
        "Homework submissions",
        "Homework submissions created or updated.",
    ),
    (
        "project.submitted",
        "Project submissions",
        "Project submissions created or updated.",
    ),
    (
        "project.review_submitted",
        "Peer reviews",
        "Project peer reviews submitted.",
    ),
    (
        "datamailer.health_warning",
        "Health warnings",
        "Datamailer health warnings.",
    ),
    (
        "exception",
        "Exceptions",
        "Unhandled Django exceptions reported through observability.",
    ),
]


@dataclass(frozen=True)
class CloudWatchDashboardEvent:
    name: str
    title: str
    description: str


class CloudWatchDashboardError(Exception):
    pass


def cloudwatch_dashboard_context(
    *,
    environment: str | None = None,
    hours: int = 24,
) -> dict:
    environment = (environment or observability_environment()).strip()
    hours = normalized_hours(hours)
    period_seconds = 3600
    namespace = getattr(
        settings,
        "CLOUDWATCH_APP_METRIC_NAMESPACE",
        "CourseManagement/App",
    )
    events = cloudwatch_dashboard_events()

    try:
        client = cloudwatch_client()
        buckets = metric_buckets(hours=hours, period_seconds=period_seconds)
        results = client.get_metric_data(
            MetricDataQueries=metric_data_queries(
                events=events,
                namespace=namespace,
                environment=environment,
                period_seconds=period_seconds,
            ),
            StartTime=buckets[0],
            EndTime=buckets[-1] + timedelta(seconds=period_seconds),
            ScanBy="TimestampAscending",
        )
    except (BotoCoreError, ClientError, NoCredentialsError) as exc:
        raise CloudWatchDashboardError(str(exc)) from exc

    return {
        "metric_series": metric_series_from_results(
            events=events,
            buckets=buckets,
            results=results,
        ),
        "environment": environment,
        "hours": hours,
        "namespace": namespace,
        "metric_name": METRIC_NAME,
        "period_label": "1 hour",
        "region": cloudwatch_region(),
    }


def cloudwatch_dashboard_error_context(
    *,
    environment: str | None = None,
    hours: int = 24,
    error: str,
) -> dict:
    return {
        "metric_series": [],
        "environment": (environment or observability_environment()).strip(),
        "hours": normalized_hours(hours),
        "namespace": getattr(
            settings,
            "CLOUDWATCH_APP_METRIC_NAMESPACE",
            "CourseManagement/App",
        ),
        "metric_name": METRIC_NAME,
        "period_label": "1 hour",
        "region": cloudwatch_region(),
        "dashboard_error": error,
    }


def cloudwatch_dashboard_events() -> list[CloudWatchDashboardEvent]:
    return [
        CloudWatchDashboardEvent(
            name=event_name,
            title=title,
            description=description,
        )
        for event_name, title, description in DEFAULT_DASHBOARD_EVENTS
    ]


def cloudwatch_client():
    kwargs = {
        "config": Config(
            connect_timeout=1,
            read_timeout=3,
            retries={"max_attempts": 1},
        )
    }
    region = cloudwatch_region()
    if region:
        kwargs["region_name"] = region
    return boto3.client("cloudwatch", **kwargs)


def cloudwatch_region() -> str:
    return (
        getattr(settings, "CLOUDWATCH_APP_METRIC_REGION", "")
        or getattr(settings, "AWS_REGION", "")
        or getattr(settings, "AWS_DEFAULT_REGION", "")
    ).strip()


def normalized_hours(hours: int) -> int:
    return hours if hours in {6, 24, 72, 168} else 24


def metric_buckets(*, hours: int, period_seconds: int) -> list:
    period = timedelta(seconds=period_seconds)
    end_bucket = floor_datetime(timezone.now(), period_seconds)
    bucket_count = max(1, hours * 3600 // period_seconds)
    return [
        end_bucket - ((bucket_count - index - 1) * period)
        for index in range(bucket_count)
    ]


def floor_datetime(value, period_seconds: int):
    timestamp = floor(value.timestamp() / period_seconds) * period_seconds
    return timezone.datetime.fromtimestamp(timestamp, tz=UTC)


def metric_data_queries(
    *,
    events: list[CloudWatchDashboardEvent],
    namespace: str,
    environment: str,
    period_seconds: int,
) -> list[dict]:
    queries = []
    for index, event in enumerate(events):
        queries.append(
            {
                "Id": f"m{index}",
                "Label": event.title,
                "MetricStat": {
                    "Metric": {
                        "Namespace": namespace,
                        "MetricName": METRIC_NAME,
                        "Dimensions": [
                            {
                                "Name": "environment",
                                "Value": environment,
                            },
                            {
                                "Name": "event",
                                "Value": event.name,
                            },
                        ],
                    },
                    "Period": period_seconds,
                    "Stat": "Sum",
                    "Unit": "Count",
                },
                "ReturnData": True,
            }
        )
    return queries


def metric_series_from_results(
    *,
    events: list[CloudWatchDashboardEvent],
    buckets: list,
    results: dict,
) -> list[dict]:
    results_by_id = {
        result["Id"]: result
        for result in results.get("MetricDataResults", [])
    }
    series = []
    for index, event in enumerate(events):
        result = results_by_id.get(f"m{index}", {})
        values_by_bucket = timestamp_values_by_bucket(result)
        values = [
            int(values_by_bucket.get(bucket, 0))
            for bucket in buckets
        ]
        max_value = max(values) if values else 0
        series.append(
            {
                "event": event.name,
                "title": event.title,
                "description": event.description,
                "total": sum(values),
                "max_value": max_value,
                "latest_value": values[-1] if values else 0,
                "points": chart_points(values, max_value=max_value),
                "has_data": any(value > 0 for value in values),
            }
        )
    return series


def timestamp_values_by_bucket(result: dict) -> dict:
    values = {}
    timestamps = result.get("Timestamps", [])
    metric_values = result.get("Values", [])
    for timestamp, value in zip(timestamps, metric_values, strict=False):
        bucket = floor_datetime(timestamp, 3600)
        values[bucket] = values.get(bucket, 0) + value
    return values


def chart_points(values: list[int], *, max_value: int) -> str:
    if not values:
        return ""

    width = 280
    height = 80
    padding = 5
    usable_width = width - (padding * 2)
    usable_height = height - (padding * 2)
    denominator = max(1, len(values) - 1)
    peak = max(1, max_value)
    points = []
    for index, value in enumerate(values):
        x = padding + (index / denominator) * usable_width
        y = height - padding - ((value / peak) * usable_height)
        points.append(f"{x:.1f},{y:.1f}")
    return " ".join(points)
