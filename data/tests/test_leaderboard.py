"""Tests for the public leaderboard data endpoint."""

import yaml

from .leaderboard_base import LeaderboardDataViewBase


class LeaderboardDataViewTestCase(LeaderboardDataViewBase):

    def test_returns_yaml(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"], "text/plain; charset=utf-8"
        )
        data = yaml.safe_load(response.content)
        self.assertEqual(data["course"], "test-course")

    def test_no_auth_required(self):
        """Endpoint is public, no token needed."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

    def test_leaderboard_ordering(self):
        response = self.client.get(self.url)
        data = yaml.safe_load(response.content)
        leaderboard = data["leaderboard"]
        self.assertEqual(len(leaderboard), 2)
        self.assertEqual(leaderboard[0]["display_name"], "Alice")
        self.assertEqual(leaderboard[0]["total_score"], 100)
        self.assertEqual(leaderboard[0]["position"], 1)
        self.assertEqual(leaderboard[1]["display_name"], "Bob")

    def test_nonexistent_course(self):
        response = self.client.get(
            "/api/courses/nonexistent/leaderboard.yaml"
        )
        self.assertEqual(response.status_code, 404)
