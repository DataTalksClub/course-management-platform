from courses.models import User
from courses.tests.leaderboard_base import LeaderboardTestBase


class LeaderboardScoreBreakdownAdminTestCase(LeaderboardTestBase):
    def test_score_breakdown_admin_button_visible_for_staff(self):
        enrollment = self.create_student("student1")
        admin_user = User.objects.create_user(username="admin", is_staff=True)

        self.client.force_login(admin_user)
        url = self.score_breakdown_url(enrollment)
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        admin_edit_url = self.admin_enrollment_edit_url(enrollment)
        self.assertContains(response, admin_edit_url)
        self.assertContains(response, "fa-cog")

    def test_score_breakdown_admin_button_hidden_for_regular_user(self):
        enrollment = self.create_student("student1")
        regular_user = User.objects.create_user(
            username="regular",
            is_staff=False,
        )

        self.client.force_login(regular_user)
        url = self.score_breakdown_url(enrollment)
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "fa-cog")

    def test_score_breakdown_admin_button_hidden_for_anonymous(self):
        enrollment = self.create_student("student1")
        url = self.score_breakdown_url(enrollment)

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "fa-cog")
