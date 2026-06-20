"""Characterization tests for calculate_wrapped_statistics.

These pin the current behaviour (platform-wide + per-user wrapped stats) so the
function can be refactored safely. The numbers below are derived by hand from
the fixture data created in setUp.
"""

from datetime import datetime

from django.test import TestCase
from django.utils import timezone

from courses.models import (
    User,
    Course,
    Homework,
    Submission,
    Project,
    ProjectSubmission,
    Enrollment,
    UserWrappedStatistics,
)
from courses.scoring import calculate_wrapped_statistics


def in_2025(month=6, day=1):
    return timezone.make_aware(datetime(2025, month, day, 12, 0, 0))


class CalculateWrappedStatisticsTest(TestCase):
    def setUp(self):
        self.course = Course.objects.create(
            slug="wrapped-course", title="Wrapped Course"
        )
        self.homework = Homework.objects.create(
            course=self.course,
            slug="hw1",
            title="HW 1",
            due_date=in_2025(),
        )
        self.project = Project.objects.create(
            course=self.course,
            slug="proj1",
            title="Project 1",
            submission_due_date=in_2025(7, 1),
            peer_review_due_date=in_2025(7, 8),
        )

        # Alice: high scorer, certificate, homework + project activity
        self.alice = User.objects.create_user(
            username="alice@test.com", email="alice@test.com"
        )
        self.alice_enrollment = Enrollment.objects.create(
            student=self.alice,
            course=self.course,
            display_name="Alice",
            total_score=100,
            certificate_url="https://certs.example.com/alice",
        )
        Submission.objects.create(
            homework=self.homework,
            student=self.alice,
            enrollment=self.alice_enrollment,
            time_spent_lectures=2.0,
            time_spent_homework=3.0,
            learning_in_public_links=["https://x/1", "https://x/2"],
            faq_contribution_url="https://faq/alice",
            submitted_at=in_2025(),
        )
        ProjectSubmission.objects.create(
            project=self.project,
            student=self.alice,
            enrollment=self.alice_enrollment,
            time_spent=5.0,
            learning_in_public_links=["https://x/3"],
            submitted_at=in_2025(7, 2),
        )

        # Bob: lower scorer, no certificate, homework only
        self.bob = User.objects.create_user(
            username="bob@test.com", email="bob@test.com"
        )
        self.bob_enrollment = Enrollment.objects.create(
            student=self.bob,
            course=self.course,
            display_name="Bob",
            total_score=50,
        )
        Submission.objects.create(
            homework=self.homework,
            student=self.bob,
            enrollment=self.bob_enrollment,
            time_spent_lectures=1.0,
            time_spent_homework=1.0,
            submitted_at=in_2025(),
        )

        self.stats = calculate_wrapped_statistics(year=2025, force=True)

    def test_platform_statistics(self):
        self.assertEqual(self.stats.total_participants, 2)
        self.assertEqual(self.stats.total_enrollments, 2)
        # Alice 2+3+5 = 10, Bob 1+1 = 2 -> 12 hours total
        self.assertEqual(self.stats.total_hours, 12.0)
        self.assertEqual(self.stats.total_certificates, 1)
        self.assertEqual(self.stats.total_points, 150)
        self.assertEqual(
            self.stats.course_stats,
            [
                {
                    "title": "Wrapped Course",
                    "slug": "wrapped-course",
                    "enrollment_count": 2,
                }
            ],
        )

    def test_leaderboard(self):
        leaderboard = self.stats.leaderboard
        self.assertEqual(len(leaderboard), 2)
        self.assertEqual(leaderboard[0]["display_name"], "Alice")
        self.assertEqual(leaderboard[0]["rank"], 1)
        self.assertEqual(leaderboard[0]["total_score"], 100)
        self.assertEqual(leaderboard[1]["display_name"], "Bob")
        self.assertEqual(leaderboard[1]["rank"], 2)

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

    def test_idempotent_recalculation(self):
        # Re-running with force should not duplicate user rows.
        again = calculate_wrapped_statistics(year=2025, force=True)
        self.assertEqual(again.id, self.stats.id)
        self.assertEqual(
            UserWrappedStatistics.objects.filter(wrapped=again).count(), 2
        )
