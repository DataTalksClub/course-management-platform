from datetime import timedelta
from unittest.mock import patch

from django.urls import reverse

from courses.models import ProjectState
from courses.project_assignment import ProjectActionStatus
from cadmin.tests.project_view_base import ProjectCadminViewTestBase


class ProjectActionViewTests(ProjectCadminViewTestBase):
    @patch("cadmin.views.projects.send_project_score_notification")
    @patch("cadmin.views.projects.score_project")
    def test_project_score_shows_message_without_notifying(
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
        send_score_notification.assert_not_called()

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
        send_score_notification.assert_not_called()

    @patch("cadmin.views.projects.send_project_score_notification")
    def test_project_notify_scores_sends_for_completed_project(
        self,
        send_score_notification,
    ):
        self.project.state = ProjectState.COMPLETED.value
        self.project.save(update_fields=["state"])
        self.login_admin()

        response = self.client.post(
            self.cadmin_project_notify_scores_url(),
            follow=True,
        )

        self.assertRedirects(response, self.cadmin_course_url())
        send_score_notification.assert_called_once_with(self.project)
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)

    @patch("cadmin.views.projects.send_project_score_notification")
    def test_project_notify_scores_requires_completed_project(
        self,
        send_score_notification,
    ):
        self.login_admin()

        response = self.client.post(
            self.cadmin_project_notify_scores_url(),
            follow=True,
        )

        self.assertRedirects(response, self.cadmin_course_url())
        send_score_notification.assert_not_called()
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)

    @patch(
        "cadmin.views.projects.send_peer_review_assignment_notification"
    )
    @patch("cadmin.views.projects.assign_peer_reviews_for_project")
    def test_project_assign_reviews_shows_message_without_notifying(
        self,
        assign_reviews,
        send_assignment_notification,
    ):
        assign_reviews.return_value = (
            ProjectActionStatus.OK,
            "Peer reviews assigned",
        )
        url = self.cadmin_project_assign_reviews_url()
        course_admin_url = self.cadmin_course_url()

        self.login_admin()
        response = self.client.post(url, follow=True)

        self.assertRedirects(response, course_admin_url)
        messages = list(response.context["messages"])
        message_count = len(messages)
        self.assertEqual(message_count, 1)
        send_assignment_notification.assert_not_called()

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

    @patch(
        "cadmin.views.projects.send_peer_review_assignment_notification"
    )
    def test_project_notify_peer_reviews_sends_after_assignment(
        self,
        send_assignment_notification,
    ):
        self.project.state = ProjectState.PEER_REVIEWING.value
        self.project.save(update_fields=["state"])
        self.login_admin()

        response = self.client.post(
            self.cadmin_project_notify_peer_reviews_url(),
            follow=True,
        )

        self.assertRedirects(response, self.cadmin_course_url())
        send_assignment_notification.assert_called_once_with(self.project)
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)

    @patch(
        "cadmin.views.projects.send_peer_review_assignment_notification"
    )
    def test_project_notify_peer_reviews_requires_assignment(
        self,
        send_assignment_notification,
    ):
        self.login_admin()

        response = self.client.post(
            self.cadmin_project_notify_peer_reviews_url(),
            follow=True,
        )

        self.assertRedirects(response, self.cadmin_course_url())
        send_assignment_notification.assert_not_called()
        messages = list(response.context["messages"])
        self.assertEqual(len(messages), 1)


class ProjectExtendDeadlineViewTests(ProjectCadminViewTestBase):
    def extend_deadline_url(self):
        kwargs = {
            "course_slug": self.course.slug,
            "project_slug": self.project.slug,
        }
        return reverse("cadmin_project_extend_deadline", kwargs=kwargs)

    def test_extend_deadline_moves_both_dates(self):
        self.login_admin()
        original_submission = self.project.submission_due_date
        original_review = self.project.peer_review_due_date

        response = self.client.post(
            self.extend_deadline_url(), {"days": 7}, follow=True
        )

        self.assertRedirects(response, self.cadmin_course_url())
        self.project.refresh_from_db()
        self.assertEqual(
            self.project.submission_due_date,
            original_submission + timedelta(days=7),
        )
        self.assertEqual(
            self.project.peer_review_due_date,
            original_review + timedelta(days=7),
        )

    def test_extend_deadline_can_redirect_back_to_submissions(self):
        self.login_admin()
        next_url = self.cadmin_project_submissions_url()

        response = self.client.post(
            self.extend_deadline_url(),
            {"days": 1, "next": next_url},
        )

        self.assertRedirects(response, next_url)

    def test_extend_deadline_rejects_invalid_days(self):
        self.login_admin()
        original_submission = self.project.submission_due_date
        original_review = self.project.peer_review_due_date

        response = self.client.post(
            self.extend_deadline_url(), {"days": 2}
        )

        self.assertRedirects(response, self.cadmin_course_url())
        self.project.refresh_from_db()
        self.assertEqual(
            self.project.submission_due_date, original_submission
        )
        self.assertEqual(
            self.project.peer_review_due_date, original_review
        )

    def test_extend_deadline_during_peer_review_moves_only_review(self):
        self.project.state = ProjectState.PEER_REVIEWING.value
        self.project.save(update_fields=["state"])
        self.login_admin()
        original_submission = self.project.submission_due_date
        original_review = self.project.peer_review_due_date

        response = self.client.post(
            self.extend_deadline_url(), {"days": 3}, follow=True
        )

        self.assertRedirects(response, self.cadmin_course_url())
        self.project.refresh_from_db()
        self.assertEqual(
            self.project.submission_due_date, original_submission
        )
        self.assertEqual(
            self.project.peer_review_due_date,
            original_review + timedelta(days=3),
        )

    def test_extend_deadline_not_allowed_when_completed(self):
        self.project.state = ProjectState.COMPLETED.value
        self.project.save(update_fields=["state"])
        self.login_admin()
        original_submission = self.project.submission_due_date
        original_review = self.project.peer_review_due_date

        response = self.client.post(
            self.extend_deadline_url(), {"days": 3}
        )

        self.assertRedirects(response, self.cadmin_course_url())
        self.project.refresh_from_db()
        self.assertEqual(
            self.project.submission_due_date, original_submission
        )
        self.assertEqual(
            self.project.peer_review_due_date, original_review
        )
