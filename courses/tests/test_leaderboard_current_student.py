from courses.models import Enrollment, User
from courses.tests.leaderboard_base import LeaderboardTestBase


class LeaderboardCurrentStudentTestCase(LeaderboardTestBase):
    def test_leaderboard_jump_to_current_student_uses_their_page(self):
        target_user, target_enrollment = (
            self.create_leaderboard_with_target_student(
                target_index=101,
                count=105,
            )
        )
        self.client.force_login(target_user)
        url = self.leaderboard_url()

        response = self.client.get(url)

        self.assert_current_student_page_link(response, target_enrollment)

    def test_leaderboard_refreshes_stale_cache_for_current_student(self):
        self.create_paginated_leaderboard(101)
        url = self.leaderboard_url()
        self.client.get(url)

        target_user = User.objects.create_user(username="current-student")
        target_enrollment = Enrollment.objects.create(
            course=self.course,
            student=target_user,
            display_name="Current Student",
            total_score=0,
            position_on_leaderboard=None,
        )

        self.client.force_login(target_user)
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["current_student_page_number"], 2)
        self.assertContains(response, f"record-{target_enrollment.id}")
        self.assertContains(
            response,
            f'?page=2#record-{target_enrollment.id}',
        )
