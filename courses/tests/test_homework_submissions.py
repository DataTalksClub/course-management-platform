from courses.tests.homework_submissions_base import (
    HomeworkSubmissionsViewTestBase,
    credentials,
)


class HomeworkSubmissionsAccessTest(HomeworkSubmissionsViewTestBase):
    def test_submissions_view_unauthenticated_redirects(self):
        url = self.submissions_url()

        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)
        redirect_url = self.homework_url()
        self.assertRedirects(response, redirect_url)

    def test_submissions_view_regular_user_denied(self):
        self.client.login(**credentials)
        url = self.submissions_url()

        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)
        redirect_url = self.homework_url()
        self.assertRedirects(response, redirect_url)

    def test_submissions_view_admin_can_access(self):
        self.login_admin()
        url = self.submissions_url()

        response = self.client.get(url, follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "cadmin/homework_submissions.html")

        context = response.context
        self.assertEqual(context["course"], self.course)
        self.assertEqual(context["homework"], self.homework)

        submissions_data = context["submissions_data"]
        submissions_count = len(submissions_data)
        self.assertEqual(submissions_count, 1)
        self.assertEqual(submissions_data[0]["submission"], self.submission)
