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
    def create_course(self):
        return Course.objects.create(
            slug="wrapped-course", title="Wrapped Course"
        )

    def create_homework(self):
        return Homework.objects.create(
            course=self.course,
            slug="hw1",
            title="HW 1",
            due_date=in_2025(),
        )

    def create_project(self):
        return Project.objects.create(
            course=self.course,
            slug="proj1",
            title="Project 1",
            submission_due_date=in_2025(7, 1),
            peer_review_due_date=in_2025(7, 8),
        )

    def create_user(self, email):
        return User.objects.create_user(username=email, email=email)

    def create_enrollment(
        self, user, display_name, total_score, certificate_url=""
    ):
        return Enrollment.objects.create(
            student=user,
            course=self.course,
            display_name=display_name,
            total_score=total_score,
            certificate_url=certificate_url,
        )

    def create_homework_submission(
        self,
        user,
        enrollment,
        lecture_hours,
        homework_hours,
        learning_links=None,
        faq_url="",
    ):
        return Submission.objects.create(
            homework=self.homework,
            student=user,
            enrollment=enrollment,
            time_spent_lectures=lecture_hours,
            time_spent_homework=homework_hours,
            learning_in_public_links=learning_links or [],
            faq_contribution_url=faq_url,
            submitted_at=in_2025(),
        )

    def create_project_submission(self, user, enrollment):
        return ProjectSubmission.objects.create(
            project=self.project,
            student=user,
            enrollment=enrollment,
            time_spent=5.0,
            learning_in_public_links=["https://x/3"],
            submitted_at=in_2025(7, 2),
        )

    def create_alice_activity(self):
        self.alice = self.create_user("alice@test.com")
        self.alice_enrollment = self.create_enrollment(
            self.alice,
            "Alice",
            100,
            certificate_url="https://certs.example.com/alice",
        )
        self.create_homework_submission(
            self.alice,
            self.alice_enrollment,
            lecture_hours=2.0,
            homework_hours=3.0,
            learning_links=["https://x/1", "https://x/2"],
            faq_url="https://faq/alice",
        )
        self.create_project_submission(self.alice, self.alice_enrollment)

    def create_bob_activity(self):
        self.bob = self.create_user("bob@test.com")
        self.bob_enrollment = self.create_enrollment(
            self.bob, "Bob", 50
        )
        self.create_homework_submission(
            self.bob,
            self.bob_enrollment,
            lecture_hours=1.0,
            homework_hours=1.0,
        )

    def setUp(self):
        self.course = self.create_course()
        self.homework = self.create_homework()
        self.project = self.create_project()
        self.create_alice_activity()
        self.create_bob_activity()
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
