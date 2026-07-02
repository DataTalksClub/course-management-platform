from django.urls import reverse

from .project_list_view_base import ProjectListViewRequestMixin


class ProjectListViewTests(ProjectListViewRequestMixin):
    def test_list_view_authenticated_no_submission(self):
        self.submission.delete()

        response = self.get_project_list_response(login=True)

        self.assert_project_list_response(response)
        self.assertFalse(response.context["has_submission"])
        self.assert_add_to_evaluation_visible(response)
        self.assertNotContains(response, "Other submissions")

    def test_list_view_authenticated_with_submission(self):
        self.peer_review.delete()

        response = self.get_project_list_response(login=True)

        self.assert_project_list_response(response)
        self.assertTrue(response.context["has_submission"])
        self.assert_add_to_evaluation_visible(response)


class ProjectListLinkViewTests(ProjectListViewRequestMixin):
    def test_project_list_links_student_to_repository(self):
        response = self.get_project_list_response()

        self.assertEqual(response.status_code, 200)
        leaderboard_url = reverse(
            "leaderboard_score_breakdown",
            kwargs={
                "course_slug": self.course.slug,
                "enrollment_id": self.enrollment.id,
            },
        )
        self.assertContains(response, leaderboard_url)
        self.assertContains(response, self.submission.github_link)
        self.assertContains(response, 'aria-label="Open repository"')
        submissions_url = reverse(
            "list_all_project_submissions", args=[self.course.slug]
        )
        self.assertContains(response, submissions_url)
