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
