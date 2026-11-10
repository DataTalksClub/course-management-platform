from django.conf import settings
from django.test import SimpleTestCase

from api.views.leaderboard_exports import (
    LEADERBOARD_DATA_CACHE_TTL,
    LEADERBOARD_YAML_CACHE_TTL,
)


class LeaderboardCacheTTLTests(SimpleTestCase):
    def test_public_leaderboard_cache_lifetime_is_bounded(self):
        self.assertLessEqual(LEADERBOARD_DATA_CACHE_TTL, 60)
        self.assertLessEqual(LEADERBOARD_YAML_CACHE_TTL, 60)
        self.assertLessEqual(settings.DASHBOARD_CACHE_TTL, 60)
