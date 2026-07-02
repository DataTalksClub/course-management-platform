from courses.tests.homework_submissions_base import (
    HomeworkSubmissionsViewTestBase,
)


class HomeworkSubmissionsListTest(HomeworkSubmissionsViewTestBase):
    def test_submissions_view_displays_all_submissions(self):
        self.create_second_submission()

        self.login_admin()
        url = self.submissions_url()

        response = self.client.get(url, follow=True)

        self.assertEqual(response.status_code, 200)
        submissions_data = response.context["submissions_data"]
        self.assertEqual(len(submissions_data), 2)
