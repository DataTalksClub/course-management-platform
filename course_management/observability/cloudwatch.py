import logging
import time
from dataclasses import dataclass

from django.conf import settings

from course_management.observability.events import AppEvent

logger = logging.getLogger(__name__)

METRIC_NAME = "AppEventCount"


@dataclass(frozen=True)
class CloudWatchMetricsConfig:
    namespace: str


class CloudWatchMetricsEventBackend:
    def record(self, event: AppEvent) -> None:
        payload = cloudwatch_metric_payload(
            event,
            config=cloudwatch_metrics_config(),
        )
        logger.info("cloudwatch_app_event", extra=payload)


def cloudwatch_metrics_config() -> CloudWatchMetricsConfig:
    namespace = getattr(
        settings,
        "CLOUDWATCH_APP_METRIC_NAMESPACE",
        "CourseManagement/App",
    )
    return CloudWatchMetricsConfig(namespace=namespace)


def cloudwatch_metric_payload(
    event: AppEvent,
    *,
    config: CloudWatchMetricsConfig,
) -> dict:
    properties = event.normalized_properties()
    environment = properties["environment"]
    payload = dict(properties)
    payload.update(
        {
            "distinct_id": event.distinct_id,
            METRIC_NAME: 1,
            "_aws": {
                "Timestamp": int(time.time() * 1000),
                "CloudWatchMetrics": [
                    {
                        "Namespace": config.namespace,
                        "Dimensions": [["environment", "event"]],
                        "Metrics": [
                            {
                                "Name": METRIC_NAME,
                                "Unit": "Count",
                            }
                        ],
                    }
                ]
            },
            "environment": environment,
            "event": event.name,
        }
    )
    return payload
