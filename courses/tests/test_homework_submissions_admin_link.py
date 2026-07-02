from courses.tests.homework_submissions_base import (
    HomeworkSubmissionsViewTestBase,
    credentials,
)


class HomeworkSubmissionsAdminLinkTest(HomeworkSubmissionsViewTestBase):
    def test_admin_link_visible_to_staff(self):
        self.login_admin()
        url = self.homework_url()

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertIn("Manage homework in cadmin", content)
        admin_url = self.cadmin_homework_submissions_url()
        self.assertIn(admin_url, content)

    def test_admin_link_not_visible_to_regular_users(self):
        self.client.login(**credentials)
        url = self.homework_url()

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertNotIn("Manage homework in cadmin", content)
