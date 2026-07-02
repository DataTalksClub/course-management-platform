"""Cache behavior tests for the public leaderboard data endpoint."""

import yaml
from unittest.mock import patch

from courses.leaderboard import update_leaderboard

from .leaderboard_base import LeaderboardDataViewBase


class LeaderboardCacheViewTestCase(LeaderboardDataViewBase):
    def test_response_is_cached(self):
        self.client.get(self.url)

        self.enrollment1.display_name = "Alice Changed"
        self.enrollment1.save()

        response = self.client.get(self.url)
        data = yaml.safe_load(response.content)
        self.assertEqual(data["leaderboard"][0]["display_name"], "Alice")

    def test_rendered_yaml_response_is_cached(self):
        self.client.get(self.url)

        with patch("api.views.leaderboard_exports.yaml.dump") as yaml_dump:
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        yaml_dump.assert_not_called()

    def test_cache_invalidation(self):
        self.client.get(self.url)

        self.enrollment1.display_name = "Alice Changed"
        self.enrollment1.save()
        update_leaderboard(self.course)

        response = self.client.get(self.url)
        data = yaml.safe_load(response.content)
        self.assertEqual(
            data["leaderboard"][0]["display_name"],
            "Alice Changed",
        )
