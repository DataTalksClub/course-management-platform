from unittest.mock import patch

from courses.project_assignment import ProjectActionStatus
from cadmin.tests.project_view_base import ProjectCadminViewTestBase


class ProjectActionViewTests(ProjectCadminViewTestBase):
    @patch("cadmin.views.projects.send_project_score_notification")
    @patch("cadmin.views.projects.score_project")
    def test_project_score_shows_message(
        self,
        score_project_mock,
        send_score_notification,
    ):
        score_project_mock.return_value = (
            ProjectActionStatus.OK,
            "Project scored",
        )
        url = self.cadmin_project_score_url()
        course_admin_url = self.cadmin_course_url()

        self.login_admin()
        response = self.client.post(url, follow=True)

        self.assertRedirects(response, course_admin_url)
        messages = list(response.context["messages"])
        message_count = len(messages)
        self.assertEqual(message_count, 1)
        send_score_notification.assert_called_once_with(self.project)

    @patch("cadmin.views.projects.send_project_score_notification")
    @patch("cadmin.views.projects.score_project")
    def test_project_score_can_redirect_back_to_project_submissions(
        self,
        score_project_mock,
        send_score_notification,
    ):
        score_project_mock.return_value = (
            ProjectActionStatus.OK,
            "Project scored",
        )
        next_url = self.cadmin_project_submissions_url()
        url = self.cadmin_project_score_url()

        self.login_admin()
        response = self.client.post(
            url, {"next": next_url}, follow=True
        )

        self.assertRedirects(response, next_url)
        send_score_notification.assert_called_once_with(self.project)

    @patch("cadmin.views.projects.send_project_score_notification")
    def test_project_assign_reviews_shows_message(
        self,
        send_score_notification,
    ):
        url = self.cadmin_project_assign_reviews_url()
        course_admin_url = self.cadmin_course_url()

        self.login_admin()
        response = self.client.post(url, follow=True)

        self.assertRedirects(response, course_admin_url)
        messages = list(response.context["messages"])
        message_count = len(messages)
        self.assertEqual(message_count, 1)
        send_score_notification.assert_not_called()

    @patch(
        "cadmin.views.projects.send_peer_review_assignment_notification"
    )
    def test_project_assign_reviews_can_redirect_back_to_project_submissions(
        self,
        send_assignment_notification,
    ):
        next_url = self.cadmin_project_submissions_url()
        url = self.cadmin_project_assign_reviews_url()

        self.login_admin()
        response = self.client.post(
            url, {"next": next_url}, follow=True
        )

        self.assertRedirects(response, next_url)
        send_assignment_notification.assert_not_called()
