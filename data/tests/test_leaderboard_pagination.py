"""Pagination tests for the public leaderboard data endpoint."""

from accounts.models import CustomUser
from courses.models import Enrollment

from .leaderboard_base import LeaderboardDataViewBase


class LeaderboardPaginationViewTestCase(LeaderboardDataViewBase):
    def create_paginated_leaderboard_entries(self):
        for i in range(3, 106):
            user = CustomUser.objects.create(
                username=f"user{i}",
                email=f"user{i}@example.com",
            )
            Enrollment.objects.create(
                student=user,
                course=self.course,
                display_name=f"User {i}",
                total_score=100 - i,
                position_on_leaderboard=i,
            )

    def assert_first_leaderboard_page(self, data):
        self.assertEqual(data["page"], 1)
        self.assertNotIn("page_size", data)
        self.assertEqual(data["total_entries"], 105)
        self.assertEqual(data["total_pages"], 2)
        self.assertTrue(data["has_next"])
        self.assertEqual(
            data["next_page"],
            "/api/courses/test-course/leaderboard.yaml?page=2",
        )
        self.assertEqual(data["next_page_number"], 2)
        self.assertEqual(len(data["leaderboard"]), 100)
        self.assertEqual(data["leaderboard"][0]["display_name"], "Alice")
        self.assertEqual(data["leaderboard"][-1]["display_name"], "User 100")

    def assert_second_leaderboard_page(self, data):
        self.assertEqual(data["page"], 2)
        self.assertEqual(len(data["leaderboard"]), 5)
        self.assertFalse(data["has_next"])
        self.assertIsNone(data["next_page"])
        self.assertIsNone(data["next_page_number"])
        self.assertEqual(
            data["previous_page"],
            "/api/courses/test-course/leaderboard.yaml?page=1",
        )
        self.assertEqual(data["previous_page_number"], 1)
        self.assertEqual(data["leaderboard"][0]["display_name"], "User 101")

    def test_leaderboard_is_paginated(self):
        self.create_paginated_leaderboard_entries()

        first_page_data = self.leaderboard_data()
        self.assert_first_leaderboard_page(first_page_data)

        second_page_data = self.leaderboard_data({"page": 2})
        self.assert_second_leaderboard_page(second_page_data)
