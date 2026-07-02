from django.urls import reverse

from courses.tests.course_leaderboard_base import (
    CourseLeaderboardViewTestBase,
)


class CourseLeaderboardScoreBreakdownTests(CourseLeaderboardViewTestBase):
    def test_leaderboard_links_to_score_breakdown_without_flag_button(self):
        self.create_leaderboard_enrollment("e1", 100, 1)

        url = self.leaderboard_url()
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "e1")
        self.assertNotContains(response, "Flag this record")

    def test_score_breakdown_has_flag_button(self):
        target = self.create_leaderboard_enrollment("e1", 100, 1)

        url = self.leaderboard_score_breakdown_url(target)
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Flag this record")

    def test_score_breakdown_prompts_owner_to_show_public_profile(self):
        self.client.force_login(self.user)

        url = self.leaderboard_score_breakdown_url()
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Show public profile")
        enrollment_url = reverse("enrollment", args=[self.course.slug])
        self.assertContains(response, f'href="{enrollment_url}"')

    def test_score_breakdown_does_not_prompt_for_other_record(self):
        target = self.create_leaderboard_enrollment("e1", 100, 1)
        self.client.force_login(self.user)

        url = self.leaderboard_score_breakdown_url(target)
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Show public profile")

    def test_score_breakdown_does_not_prompt_when_profile_public(self):
        self.enrollment.display_public_profile = True
        self.enrollment.save()
        self.client.force_login(self.user)

        url = self.leaderboard_score_breakdown_url()
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Show public profile")

    def test_score_breakdown_shows_score_equations(self):
        self.set_homework_score_breakdown_fixture()
        self.set_project_score_breakdown_fixture()

        url = self.leaderboard_score_breakdown_url()
        response = self.client.get(url)

        self.assert_score_equations(response)
        self.assert_score_breakdown_links(response)
