from django.test import TestCase
from django.urls import reverse

from courses.models import (
    User,
    WrappedStatistics,
    UserWrappedStatistics,
)


class WrappedViewTests(TestCase):
    def create_user(self):
        return User.objects.create_user(
            username="alice@example.com",
            email="alice@example.com",
            password="test",
        )

    def create_wrapped_statistics(self):
        return WrappedStatistics.objects.create(
            year=2025,
            is_visible=True,
            total_participants=10,
            total_enrollments=12,
            total_hours=42.5,
            total_certificates=3,
            total_points=900,
            course_stats=[
                {"title": "Course 1", "slug": "course-1"},
                {"title": "Course 2", "slug": "course-2"},
                {"title": "Course 3", "slug": "course-3"},
                {"title": "Course 4", "slug": "course-4"},
                {"title": "Course 5", "slug": "course-5"},
            ],
            leaderboard=[
                {
                    "student_id": self.user.id,
                    "display_name": "Alice",
                    "rank": 1,
                    "total_score": 100,
                }
            ],
        )

    def create_user_wrapped_statistics(self):
        return UserWrappedStatistics.objects.create(
            wrapped=self.wrapped,
            user=self.user,
            total_points=100,
            total_hours=7.5,
            homework_count=2,
            project_count=1,
            peer_reviews_given=3,
            learning_in_public_count=4,
            faq_contributions_count=1,
            certificates_earned=1,
            courses=[
                {
                    "title": "Course 1",
                    "slug": "course-1",
                    "score": 100,
                    "enrollment_id": 1,
                }
            ],
            rank=1,
            display_name="Alice",
        )

    def setUp(self):
        self.user = self.create_user()
        self.wrapped = self.create_wrapped_statistics()
        self.user_wrapped = self.create_user_wrapped_statistics()

    def test_wrapped_view_shows_no_data_when_missing(self):
        wrapped_url = reverse("wrapped", args=[2024])
        response = self.client.get(wrapped_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "courses/wrapped.html")
        self.assertTrue(response.context["no_data"])
        self.assertEqual(response.context["year"], 2024)

    def test_wrapped_view_uses_visible_platform_and_user_stats(self):
        self.client.force_login(self.user)

        wrapped_url = reverse("wrapped", args=[2025])
        response = self.client.get(wrapped_url)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["no_data"])
        self.assertEqual(response.context["user_rank"], 1)
        self.assertEqual(
            response.context["platform_stats"]["total_points"], 900
        )
        course_stats_count = len(
            response.context["platform_stats"]["course_stats"]
        )
        self.assertEqual(
            course_stats_count,
            4,
        )
        self.assertEqual(
            response.context["user_stats"]["total_points"], 100
        )
        self.assertEqual(
            response.context["user_stats"]["total_hours"], 7.5
        )
        self.assertEqual(
            response.context["leaderboard"], self.wrapped.leaderboard
        )

    def test_wrapped_view_hides_invisible_statistics(self):
        self.wrapped.is_visible = False
        self.wrapped.save(update_fields=["is_visible"])

        wrapped_url = reverse("wrapped", args=[2025])
        response = self.client.get(wrapped_url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["no_data"])

    def test_user_wrapped_view_shows_shareable_user_stats(self):
        user_wrapped_url = reverse("user_wrapped", args=[2025, self.user.id])
        response = self.client.get(user_wrapped_url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "courses/user_wrapped.html")
        self.assertFalse(response.context["no_activity"])
        self.assertEqual(response.context["display_name"], "Alice")
        self.assertEqual(response.context["user_rank"], 1)
        self.assertEqual(
            response.context["user_stats"]["courses"],
            self.user_wrapped.courses,
        )
        self.assertEqual(
            response.context["twitter_text"],
            (
                "Check out my @DataTalksClub Wrapped 2025! "
                "I earned 100 points and spent 7.5 hours learning!"
            ),
        )

    def test_user_wrapped_view_shows_no_activity_without_user_stats(
        self,
    ):
        other_user = User.objects.create_user(
            username="bob@example.com",
            email="bob@example.com",
        )

        user_wrapped_url = reverse(
            "user_wrapped", args=[2025, other_user.id]
        )
        response = self.client.get(user_wrapped_url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["no_activity"])
        self.assertEqual(response.context["user"], other_user)
        self.assertEqual(response.context["viewed_user"], other_user)
        self.assertEqual(
            response.context["display_name"], "bob@example.com"
        )
