from django.core.cache import cache
from django.urls import reverse

import yaml

from courses.leaderboard import update_leaderboard
from courses.tests.leaderboard_base import LeaderboardTestBase
from courses.views.course_leaderboard_data import (
    CurrentLeaderboardStudent,
    get_leaderboard_data,
)


class LeaderboardScoringTestCase(LeaderboardTestBase):
    def test_leaderboard_updates_totals_and_ranks_in_one_update(self):
        enrollments = self.create_leaderboard_fixture()
        with self.assertNumQueries(4):
            update_leaderboard(self.course)
        self.assert_leaderboard_scores(enrollments)

    def test_leaderboard(self):
        enrollments = self.create_leaderboard_fixture()

        update_leaderboard(self.course)

        self.assert_leaderboard_scores(enrollments)

    def test_leaderboard_cache_uses_database_version(self):
        enrollment = self.create_student("student1")
        homework = self.create_homework(1)
        submission = self.submit_homework(homework, enrollment, score=100)
        old_version = self.course.leaderboard_cache_version
        old_cache_key = f"leaderboard:{self.course.id}:v{old_version}"
        stale_data = [{"id": enrollment.id, "total_score": -1}]
        cache.set(old_cache_key, stale_data, 3600)

        update_leaderboard(self.course)
        self.course.refresh_from_db()

        self.assertEqual(
            self.course.leaderboard_cache_version,
            old_version + 1,
        )
        self.assertEqual(cache.get(old_cache_key), stale_data)
        current_data = get_leaderboard_data(
            self.course,
            CurrentLeaderboardStudent(None, None),
        )
        self.assertEqual(current_data[0]["total_score"], 100)

        submission.total_score = 180
        submission.save(update_fields=["total_score"])
        update_leaderboard(self.course)

        response = self.client.get(
            reverse(
                "api_course_leaderboard",
                kwargs={"course_slug": self.course.slug},
            )
        )
        self.assertEqual(response.status_code, 200)
        exported_data = yaml.safe_load(response.content)
        self.assertEqual(exported_data["leaderboard"][0]["total_score"], 180)

        for _ in range(19):
            response = self.client.get(
                reverse(
                    "api_course_leaderboard",
                    kwargs={"course_slug": self.course.slug},
                )
            )
            exported_data = yaml.safe_load(response.content)
            self.assertEqual(
                exported_data["leaderboard"][0]["total_score"],
                180,
            )
