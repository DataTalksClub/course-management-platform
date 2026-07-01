from courses.models import (
    ProjectSubmission,
    ProjectState,
)
from courses.tests.project_view_base import (
    ProjectViewTestBase,
)

class ProjectViewTestCase(ProjectViewTestBase):

    def test_project_detail_unauthenticated_no_submission(self):
        response = self.client.get(self.project_url())
        self.assertEqual(response.status_code, 200)

        context = response.context
        submission = context["submission"]

        self.assertIsNone(submission)

        self.assertFalse(context["is_authenticated"])
        self.assertFalse(context["disabled"])
        self.assertTrue(context["accepting_submissions"])

        self.assertEqual(context["project"], self.project)
        self.assertEqual(context["course"], self.course)

    def test_project_detail_displays_optional_instructions_url(self):
        self.project.instructions_url = (
            "https://example.com/project-instructions"
        )
        self.project.save()

        response = self.client.get(self.project_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Instructions")
        self.assertContains(response, self.project.instructions_url)
        self.assertContains(response, "fas fa-external-link-alt")

    def test_project_detail_hides_missing_instructions_url(self):
        self.project.instructions_url = ""
        self.project.save()

        response = self.client.get(self.project_url())

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Instructions")

    def test_project_detail_authenticated_certificate_name_is_used(
        self,
    ):
        self.enrollment.display_name = "Display Name"
        self.enrollment.save()
        self.user.certificate_name = "Certificate Name"
        self.user.save()

        response = self.authenticated_project_response()
        self.assertEqual(response.status_code, 200)

        context = response.context
        certificate_name = context["certificate_name"]

        self.assertEqual(certificate_name, "Certificate Name")

    def test_project_detail_authenticated_without_submission(self):
        self.project.learning_in_public_cap_project = 7
        self.project.faq_contribution_field = True
        self.project.save()

        response = self.authenticated_project_response()
        self.assertEqual(response.status_code, 200)

        context = response.context

        submission = context["submission"]
        self.assertIsNone(submission)

        self.assertTrue(context["is_authenticated"])
        self.assertContains(response, "Status: Not saved yet")
        self.assertContains(response, "Save submission")
        self.assertContains(
            response,
            "https://datatalks.club/docs/courses/course-management-platform/learning-in-public/",
        )
        self.assertContains(
            response,
            "https://datatalks.club/docs/courses/faq/",
        )
        self.assert_save_submission_copy(response)

    def test_project_detail_authenticated_with_submission_copy(self):
        ProjectSubmission.objects.create(
            project=self.project,
            student=self.user,
            enrollment=self.enrollment,
            github_link="https://github.com/test/project",
            commit_id="abc1234",
        )

        response = self.authenticated_project_response()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Last saved at:")
        self.assertContains(response, "Update submission")
        self.assert_save_submission_copy(response)

    def test_project_detail_when_peer_reviewing(self):
        self.project.state = ProjectState.PEER_REVIEWING.value
        self.project.save()

        response = self.authenticated_project_response()
        self.assertEqual(response.status_code, 200)

        context = response.context

        self.assertEqual(context["project"], self.project)
        self.assertTrue(context["disabled"])

    def test_project_detail_with_scored_project(self):
        self.project.state = ProjectState.COMPLETED.value
        self.project.save()

        response = self.authenticated_project_response()
        self.assertEqual(response.status_code, 200)
        self.assertIn("project", response.context)
        # Check if the context has 'disabled' as True
        self.assertTrue(response.context["disabled"])
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
