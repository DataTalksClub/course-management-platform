from django.core.cache import cache

from courses.leaderboard import update_leaderboard
from courses.tests.leaderboard_base import LeaderboardTestBase


class LeaderboardScoringTestCase(LeaderboardTestBase):
    def test_leaderboard(self):
        enrollments = self.create_leaderboard_fixture()

        update_leaderboard(self.course)

        self.assert_leaderboard_scores(enrollments)

    def test_leaderboard_cache_invalidation(self):
        enrollment1 = self.create_student("student1")
        enrollment2 = self.create_student("student2")
        homework = self.create_homework(1)
        self.submit_homework(homework, enrollment1, score=100)
        self.submit_homework(homework, enrollment2, score=50)

        update_leaderboard(self.course)

        cache_key = f"leaderboard:{self.course.id}"
        cache.set(cache_key, "test_value", 3600)
        cached_value = cache.get(cache_key)
        self.assertEqual(cached_value, "test_value")

        update_leaderboard(self.course)

        invalidated_value = cache.get(cache_key)
        self.assertIsNone(invalidated_value)
