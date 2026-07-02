from courses.tests.leaderboard_base import LeaderboardTestBase


class LeaderboardPaginationTestCase(LeaderboardTestBase):
    def test_leaderboard_is_paginated_by_100(self):
        self.create_paginated_leaderboard(105)
        url = self.leaderboard_url()

        response = self.client.get(url)
        self.assert_first_leaderboard_page(response)

        response = self.client.get(url, {"page": 2})
        self.assert_second_leaderboard_page(response)
