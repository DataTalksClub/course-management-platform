from django.urls import reverse

from courses.models import (
    PeerReview,
    ProjectState,
    ProjectSubmission,
)
from courses.tests.project_eval_base import (
    ProjectEvaluationTestBase,
    credentials,
)


class ProjectEvaluationViewTestCase(ProjectEvaluationTestBase):
    def test_eval_view_authenticated_no_submission(self):
        self.project.state = ProjectState.PEER_REVIEWING.value
        self.project.save()
        self.submission.delete()

        self.client.login(**credentials)
        url = reverse(
            "projects_eval",
            args=[self.course.slug, self.project.slug],
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "projects/eval.html")
        self.assertFalse(response.context["has_submission"])
        self.assertContains(
            response,
            "you can still volunteer to evaluate submissions",
            status_code=200,
        )
        self.assertNotContains(
            response,
            "Review progress",
            status_code=200,
        )

    def test_eval_view_shows_optional_reviews_without_submission(self):
        self.project.state = ProjectState.PEER_REVIEWING.value
        self.project.save()
        self.submission.delete()
        volunteer_submission = ProjectSubmission.objects.create(
            project=self.project,
            student=self.user,
            enrollment=self.enrollment,
            github_link="https://github.com/example/volunteer",
            commit_id="abcdef1",
            volunteer_review_only=True,
        )
        PeerReview.objects.create(
            submission_under_evaluation=self.other_submission,
            reviewer=volunteer_submission,
            note_to_peer="",
            optional=True,
        )

        self.client.login(**credentials)
        response = self.client.get(
            reverse(
                "projects_eval",
                args=[self.course.slug, self.project.slug],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["has_submission"])
        self.assertContains(response, "Selected reviews")
        self.assertContains(
            response,
            "these reviews are for practice and feedback",
        )
        self.assertContains(response, self.other_enrollment.display_name)
        self.assertNotContains(response, "Review progress")

    def test_eval_view_authenticated_with_submission(self):
        self.project.state = ProjectState.PEER_REVIEWING.value
        self.project.save()
        self.client.login(**credentials)
        url = reverse(
            "projects_eval",
            args=[self.course.slug, self.project.slug],
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "projects/eval.html")
        self.assertTrue(response.context["has_submission"])
        self.assertNotContains(
            response,
            "you did not submit your project",
            status_code=200,
        )
        self.assertContains(
            response,
            "Evaluate",
            status_code=200,
        )

    def test_eval_view_separates_assigned_and_selected_reviews(self):
        self.project.state = ProjectState.PEER_REVIEWING.value
        self.project.save()
        PeerReview.objects.create(
            submission_under_evaluation=self.other_submission,
            reviewer=self.submission,
            note_to_peer="",
            optional=True,
        )

        self.client.login(**credentials)
        response = self.client.get(
            reverse(
                "projects_eval",
                args=[self.course.slug, self.project.slug],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Review progress")
        self.assertContains(response, "Selected reviews")
        self.assertEqual(len(response.context["assigned_reviews"]), 1)
        self.assertEqual(len(response.context["selected_reviews"]), 1)

    def test_eval_view_shows_closed_message_when_project_is_not_peer_reviewing(
        self,
    ):
        self.project.state = ProjectState.COMPLETED.value
        self.project.save()
        self.client.login(**credentials)
        url = reverse(
            "projects_eval",
            args=[self.course.slug, self.project.slug],
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "projects/eval.html")
        self.assertContains(
            response,
            "Peer review form is closed.",
            status_code=200,
        )
        self.assertNotContains(
            response,
            "Review progress",
            status_code=200,
        )

    def test_eval_view_shows_no_submission_closed_message_when_completed(self):
        self.project.state = ProjectState.COMPLETED.value
        self.project.save()
        self.submission.delete()
        self.client.login(**credentials)
        url = reverse(
            "projects_eval",
            args=[self.course.slug, self.project.slug],
        )

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "projects/eval.html")
        self.assertContains(
            response,
            "submission window is closed",
            status_code=200,
        )
        self.assertNotContains(
            response,
            "Submission details",
            status_code=200,
        )
