from courses.models import UserWrappedStatistics

from .wrapped_statistics_base import WrappedStatisticsTestBase


class WrappedUserStatisticsTest(WrappedStatisticsTestBase):
    def test_user_statistics_alice(self):
        alice_stats = UserWrappedStatistics.objects.get(
            wrapped=self.stats, user=self.alice
        )

        self.assertEqual(alice_stats.total_points, 100)
        self.assertEqual(alice_stats.total_hours, 10.0)
        self.assertEqual(alice_stats.homework_count, 1)
        self.assertEqual(alice_stats.project_count, 1)
        self.assertEqual(alice_stats.peer_reviews_given, 0)
        self.assertEqual(alice_stats.learning_in_public_count, 3)
        self.assertEqual(alice_stats.faq_contributions_count, 1)
        self.assertEqual(alice_stats.certificates_earned, 1)
        self.assertEqual(alice_stats.rank, 1)
        self.assertEqual(alice_stats.display_name, "Alice")

    def test_user_statistics_bob(self):
        bob_stats = UserWrappedStatistics.objects.get(
            wrapped=self.stats, user=self.bob
        )

        self.assertEqual(bob_stats.total_points, 50)
        self.assertEqual(bob_stats.total_hours, 2.0)
        self.assertEqual(bob_stats.homework_count, 1)
        self.assertEqual(bob_stats.project_count, 0)
        self.assertEqual(bob_stats.learning_in_public_count, 0)
        self.assertEqual(bob_stats.faq_contributions_count, 0)
        self.assertEqual(bob_stats.certificates_earned, 0)
        self.assertEqual(bob_stats.rank, 2)
        self.assertEqual(bob_stats.display_name, "Bob")
