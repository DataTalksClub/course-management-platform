from unittest.mock import patch

from django.test import override_settings
from django.urls import reverse

from data.models import DatamailerOutboxEvent, DatamailerOutboxStatus
from courses.models import (
    Enrollment,
    ProjectState,
    ProjectSubmission,
)
from cadmin.tests.project_view_base import (
    admin_credentials,
    ProjectCadminViewTestBase,
)


class ProjectCadminViewTests(ProjectCadminViewTestBase):
    def assert_project_submission_actions(self, response):
        project_url = self.project_url()
        django_admin_url = (
            f"/admin/courses/project/{self.project.id}/change/"
        )
        assign_reviews_url = self.cadmin_project_assign_reviews_url()

        self.assertContains(response, project_url)
        self.assertContains(response, django_admin_url)
        self.assertContains(response, "Assign peer reviews")
        self.assertContains(response, assign_reviews_url)

    def assert_project_scoring_action(self, response):
        score_url = self.cadmin_project_score_url()

        self.assertContains(response, "Score projects")
        self.assertContains(response, score_url)

    def assert_peer_review_notification_action(self, response):
        notify_url = self.cadmin_project_notify_peer_reviews_url()

        self.assertContains(response, "Notify students of peer reviews")
        self.assertContains(response, notify_url)

    def assert_project_score_notification_action(self, response):
        notify_url = self.cadmin_project_notify_scores_url()

        self.assertContains(response, "Notify students of scores")
        self.assertContains(response, notify_url)

    def assert_first_project_submissions_page(self, response):
        self.assertEqual(response.status_code, 200)
        submissions = response.context["submissions"]
        submission_count = len(submissions)
        self.assertEqual(submission_count, 50)
        self.assertContains(response, 'href="?page=2"')
        self.assertContains(response, 'aria-label="Next page"')
        self.assertNotContains(response, "First")
        self.assertNotContains(response, "Last")

    def assert_second_project_submissions_page(self, response):
        self.assertEqual(response.status_code, 200)
        submissions = response.context["submissions"]
        submission_count = len(submissions)
        self.assertEqual(submission_count, 5)
        self.assertContains(response, 'href="?page=1"')
        self.assertContains(response, 'aria-label="Previous page"')

    def test_project_submissions_redirect_from_courses(self):
        url = self.project_submissions_url()

        self.client.login(**admin_credentials)
        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)
        self.assertIn("cadmin", response.url)

    def test_cadmin_project_submissions_staff_allowed(self):
        url = self.cadmin_project_submissions_url()

        self.client.login(**admin_credentials)
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.project.title)

    def test_cadmin_project_submissions_shows_project_actions(self):
        url = self.cadmin_project_submissions_url()

        self.login_admin()
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assert_project_submission_actions(response)

        self.project.state = ProjectState.PEER_REVIEWING.value
        self.project.save(update_fields=["state"])

        response = self.client.get(url)

        self.assert_project_scoring_action(response)
        self.assert_peer_review_notification_action(response)

        self.project.state = ProjectState.COMPLETED.value
        self.project.save(update_fields=["state"])

        response = self.client.get(url)

        self.assert_project_score_notification_action(response)

    def test_project_submission_email_links_to_leaderboard_record(self):
        """Project submission email links to the student's leaderboard record."""
        enrollment = Enrollment.objects.create(
            student=self.user,
            course=self.course,
            display_name="Test Student",
        )
        ProjectSubmission.objects.create(
            project=self.project,
            student=self.user,
            enrollment=enrollment,
            total_score=10,
        )
        url = self.cadmin_project_submissions_url()
        leaderboard_url = self.leaderboard_score_breakdown_url(
            enrollment
        )

        self.client.login(**admin_credentials)
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, leaderboard_url)

    def test_project_submission_search_finds_records_beyond_first_page(
        self,
    ):
        self.create_project_search_submissions(30)
        url = self.cadmin_project_submissions_url()

        self.client.login(**admin_credentials)
        response = self.client.get(url, {"q": "project-student-29"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "project-student-29@example.com")
        self.assertNotContains(
            response, "project-student-00@example.com"
        )

    def test_project_submissions_paginated_by_50(self):
        self.create_project_page_submissions(55)
        url = self.cadmin_project_submissions_url()

        self.login_admin()
        response = self.client.get(url)
        self.assert_first_project_submissions_page(response)

        response = self.client.get(url, {"page": 2})
        self.assert_second_project_submissions_page(response)


RELAY_SETTINGS = {
    "RELAY_URL": "https://relay.example.com",
    "RELAY_API_KEY": "test-key",
    "RELAY_CLIENT": "test-client",
    "RELAY_AUDIENCE": "test-audience",
}


class ProjectCadminScoringActionTests(ProjectCadminViewTestBase):
    @override_settings(**RELAY_SETTINGS)
    @patch("cadmin.views.projects.check_relay_availability", return_value=(True, ""))
    @patch("cadmin.views.projects.queue_project_score_notification")
    def test_project_notify_scores_sends_notification(
        self, send_score_notification, mock_check_relay
    ):
        """The notify action queues score emails for a completed project."""
        self.project.state = ProjectState.COMPLETED.value
        self.project.save(update_fields=["state"])
        self.login_admin()
        url = reverse(
            "cadmin_project_notify_scores",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )

        response = self.client.post(url, follow=True)

        self.assertRedirects(response, self.cadmin_course_url())
        send_score_notification.assert_called_once_with(self.project)
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].level_tag, "success")

    @override_settings(**RELAY_SETTINGS)
    @patch("cadmin.views.projects.check_relay_availability")
    @patch("cadmin.views.projects.queue_project_score_notification")
    def test_project_notify_scores_shows_warning_when_relay_unavailable(
        self, send_score_notification, mock_check_relay
    ):
        """When Relay is unavailable, notify-scores still queues but shows a clear warning."""
        mock_check_relay.return_value = (
            False,
            "Relay service is not ready (status=not_ready)",
        )
        self.project.state = ProjectState.COMPLETED.value
        self.project.save(update_fields=["state"])
        self.login_admin()
        url = reverse(
            "cadmin_project_notify_scores",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )

        response = self.client.post(url, follow=True)

        self.assertRedirects(response, self.cadmin_course_url())
        send_score_notification.assert_called_once_with(self.project)
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].level_tag, "warning")
        self.assertIn("Relay is currently unavailable", messages[0].message)
        self.assertIn("Relay service is not ready", messages[0].message)

    @patch("cadmin.views.projects.queue_project_score_notification")
    def test_project_notify_scores_shows_warning_when_relay_not_configured(
        self, send_score_notification
    ):
        """When Relay is not configured, notify-scores still queues but shows a clear warning."""
        self.project.state = ProjectState.COMPLETED.value
        self.project.save(update_fields=["state"])
        self.login_admin()
        url = reverse(
            "cadmin_project_notify_scores",
            kwargs={
                "course_slug": self.course.slug,
                "project_slug": self.project.slug,
            },
        )

        response = self.client.post(url, follow=True)

        self.assertRedirects(response, self.cadmin_course_url())
        send_score_notification.assert_called_once_with(self.project)
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].level_tag, "warning")
        self.assertIn("Relay is not configured", messages[0].message)

    def test_project_submissions_page_shows_score_notification_failure(self):
        """Project submissions page shows a clear banner when score notification delivery failed or is retrying."""
        self.project.state = ProjectState.COMPLETED.value
        self.project.save(update_fields=["state"])
        self.login_admin()

        DatamailerOutboxEvent.objects.create(
            event_id="evt-proj-score-retry",
            event_type="project.score_notification",
            idempotency_key=f"project-score:{self.course.slug}:{self.project.slug}",
            ordering_key="test-ordering-key",
            status=DatamailerOutboxStatus.RETRYING,
            attempt_count=2,
            last_error="500 Server Error: Internal Server Error for url: https://relay.datatalks.club/api/recipient-lists/members/bulk-upsert",
        )

        submissions_url = self.cadmin_project_submissions_url()
        response = self.client.get(submissions_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Score notifications could not be delivered")
        self.assertContains(response, "500 Server Error")
        self.assertContains(response, "retrying automatically")

    def test_project_course_admin_page_shows_score_notification_failure_badge(self):
        """Course admin page displays a warning badge when project score notification delivery failed/is retrying."""
        self.project.state = ProjectState.COMPLETED.value
        self.project.save(update_fields=["state"])
        self.login_admin()

        DatamailerOutboxEvent.objects.create(
            event_id="evt-proj-score-fail",
            event_type="project.score_notification",
            idempotency_key=f"project-score:{self.course.slug}:{self.project.slug}",
            ordering_key="test-ordering-key",
            status=DatamailerOutboxStatus.RETRYING,
            attempt_count=1,
            last_error="Relay service is not ready",
        )

        course_url = self.cadmin_course_url()
        response = self.client.get(course_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Notifications retrying")

