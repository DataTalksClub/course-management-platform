"""Characterization tests for calculate_wrapped_statistics.

These pin the current behaviour so the function can be refactored safely. The
numbers below are derived by hand from the fixture data created in setUp.
"""

from .wrapped_statistics_base import WrappedStatisticsTestBase


class WrappedPlatformStatisticsTest(WrappedStatisticsTestBase):
    def test_platform_statistics(self):
        self.assertEqual(self.stats.total_participants, 2)
        self.assertEqual(self.stats.total_enrollments, 2)
        # Alice 2+3+5 = 10, Bob 1+1 = 2 -> 12 hours total
        self.assertEqual(self.stats.total_hours, 12.0)
        self.assertEqual(self.stats.total_certificates, 1)
        self.assertEqual(self.stats.total_points, 150)
        expected_course_stats = [
            {
                "title": "Wrapped Course",
                "slug": "wrapped-course",
                "enrollment_count": 2,
            }
        ]
        self.assertEqual(self.stats.course_stats, expected_course_stats)

    def test_leaderboard(self):
        leaderboard = self.stats.leaderboard
        self.assertEqual(len(leaderboard), 2)
        self.assertEqual(leaderboard[0]["display_name"], "Alice")
        self.assertEqual(leaderboard[0]["rank"], 1)
        self.assertEqual(leaderboard[0]["total_score"], 100)
        self.assertEqual(leaderboard[1]["display_name"], "Bob")
        self.assertEqual(leaderboard[1]["rank"], 2)
