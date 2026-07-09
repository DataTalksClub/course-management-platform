from datetime import UTC, datetime
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from course_management.observability.cloudwatch_dashboard import (
    cloudwatch_dashboard_context,
)
from courses.models import Course, User


USER_CREDENTIALS = {
    "username": "user@test.com",
    "password": "12345",
}

ADMIN_CREDENTIALS = {
    "username": "admin@test.com",
    "password": "admin123",
}


class CloudWatchDashboardViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        User.objects.create_user(
            email="user@test.com",
            **USER_CREDENTIALS,
        )
        User.objects.create_user(
            email="admin@test.com",
            is_staff=True,
            **ADMIN_CREDENTIALS,
        )

    def dashboard_context(self):
        return {
            "metric_series": [
                {
                    "event": "registration.submitted",
                    "title": "Registrations",
                    "description": "Landing page registrations submitted.",
                    "total": 5,
                    "max_value": 3,
                    "latest_value": 3,
                    "points": "5.0,75.0 275.0,5.0",
                    "has_data": True,
                }
            ],
            "environment": "dev",
            "hours": 24,
            "namespace": "CMP/Test",
            "metric_name": "AppEventCount",
            "period_label": "1 hour",
            "region": "eu-central-1",
        }

    @patch(
        "cadmin.views.observability.cloudwatch_dashboard_context",
    )
    def test_cloudwatch_dashboard_staff_allowed(self, context_mock):
        context_mock.return_value = self.dashboard_context()
        url = reverse("cadmin_cloudwatch_dashboard")

        self.client.login(**ADMIN_CREDENTIALS)
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CloudWatch metrics")
        self.assertContains(response, "Registrations")
        self.assertContains(response, "registration.submitted")
        self.assertContains(response, "CMP/Test")
        context_mock.assert_called_once_with(environment=None, hours=24)

    def test_cloudwatch_dashboard_non_staff_denied(self):
        url = reverse("cadmin_cloudwatch_dashboard")

        self.client.login(**USER_CREDENTIALS)
        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)

    def test_course_list_links_to_cloudwatch_dashboard(self):
        Course.objects.create(
            slug="test-course",
            title="Test Course",
            description="Test Course Description",
        )
        url = reverse("cadmin_course_list")
        cloudwatch_url = reverse("cadmin_cloudwatch_dashboard")

        self.client.login(**ADMIN_CREDENTIALS)
        response = self.client.get(url)

        self.assertContains(response, cloudwatch_url)
        self.assertContains(response, "CloudWatch")


class CloudWatchDashboardContextTests(TestCase):
    @override_settings(
        OBSERVABILITY_ENVIRONMENT="dev",
        CLOUDWATCH_APP_METRIC_NAMESPACE="CMP/Test",
        CLOUDWATCH_APP_METRIC_REGION="eu-central-1",
    )
    @patch(
        "course_management.observability.cloudwatch_dashboard.timezone.now",
        return_value=datetime(2026, 7, 9, 12, 35, tzinfo=UTC),
    )
    @patch("course_management.observability.cloudwatch_dashboard.boto3.client")
    def test_cloudwatch_dashboard_context_builds_metric_series(
        self,
        boto3_client_mock,
        now_mock,
    ):
        cloudwatch = boto3_client_mock.return_value
        cloudwatch.get_metric_data.return_value = {
            "MetricDataResults": [
                {
                    "Id": "m0",
                    "Timestamps": [
                        datetime(2026, 7, 9, 11, tzinfo=UTC),
                        datetime(2026, 7, 9, 12, tzinfo=UTC),
                    ],
                    "Values": [2.0, 3.0],
                }
            ]
        }

        context = cloudwatch_dashboard_context(hours=6)

        first_series = context["metric_series"][0]
        self.assertEqual(first_series["event"], "registration.submitted")
        self.assertEqual(first_series["total"], 5)
        self.assertEqual(first_series["latest_value"], 3)
        self.assertTrue(first_series["has_data"])
        self.assertEqual(context["environment"], "dev")
        self.assertEqual(context["region"], "eu-central-1")

        boto3_client_mock.assert_called_once()
        self.assertEqual(boto3_client_mock.call_args.args, ("cloudwatch",))
        self.assertEqual(
            boto3_client_mock.call_args.kwargs["region_name"],
            "eu-central-1",
        )
        query = cloudwatch.get_metric_data.call_args.kwargs[
            "MetricDataQueries"
        ][0]
        self.assertEqual(query["MetricStat"]["Metric"]["Namespace"], "CMP/Test")
        self.assertEqual(
            query["MetricStat"]["Metric"]["Dimensions"],
            [
                {"Name": "environment", "Value": "dev"},
                {"Name": "event", "Value": "registration.submitted"},
            ],
        )
        now_mock.assert_called()
