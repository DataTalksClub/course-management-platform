from courses.models import UserWrappedStatistics
from courses.wrapped_statistics.calculator import calculate_wrapped_statistics

from .wrapped_statistics_base import WrappedStatisticsTestBase


class WrappedRecalculationTest(WrappedStatisticsTestBase):
    def test_idempotent_recalculation(self):
        again = calculate_wrapped_statistics(year=2025, force=True)
        wrapped_statistics_count = UserWrappedStatistics.objects.filter(
            wrapped=again
        ).count()

        self.assertEqual(again.id, self.stats.id)
        self.assertEqual(wrapped_statistics_count, 2)
