from django.test import TestCase

from accounts.models import CustomUser, Token
from courses.models import (
    Course,
    CourseRegistration,
    Enrollment,
    ReferralReward,
    RegistrationCampaign,
)


class CourseReferralsApiTests(TestCase):
    def setUp(self):
        self.course = Course.objects.create(
            title="Test Course",
            slug="test-course",
            requires_registration_approval=True,
        )
        self.campaign = RegistrationCampaign.objects.create(
            slug="test-campaign",
            title="Test Campaign",
            current_course=self.course,
            is_active=True,
        )
        self.staff_user = CustomUser.objects.create_user(
            username="staff@example.com",
            email="staff@example.com",
            password="pw",
            is_staff=True,
        )
        self.staff_token = Token.objects.create(user=self.staff_user)
        self.student_user = CustomUser.objects.create_user(
            username="student@example.com",
            email="student@example.com",
            password="pw",
        )
        self.student_token = Token.objects.create(user=self.student_user)

    def test_referrals_requires_staff_token(self):
        url = f"/api/courses/{self.course.slug}/referrals/"
        self.assertEqual(self.client.get(url).status_code, 401)
        resp = self.client.get(
            url, HTTP_AUTHORIZATION=f"Token {self.student_token.key}"
        )
        self.assertEqual(resp.status_code, 403)

    def test_referrals_returns_aggregate_counts_without_pii(self):
        referrer = CourseRegistration.objects.create(
            campaign=self.campaign,
            course=self.course,
            user=self.student_user,
            email=self.student_user.email,
            name="Referrer",
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.DATA_ENGINEER,
            status=CourseRegistration.Status.APPROVED,
        )
        CourseRegistration.objects.create(
            campaign=self.campaign,
            course=self.course,
            email="invitee1@example.com",
            name="Invitee 1",
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.DATA_ENGINEER,
            referred_by=referrer,
            status=CourseRegistration.Status.APPROVED,
        )
        resp = self.client.get(
            f"/api/courses/{self.course.slug}/referrals/",
            HTTP_AUTHORIZATION=f"Token {self.staff_token.key}",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["course"], self.course.slug)
        self.assertEqual(data["successful_referrals_count"], 1)
        self.assertEqual(data["unique_referrers_count"], 1)
        self.assertEqual(data["total_bonus_points_awarded"], 1)
        self.assertEqual(data["enrollments_with_bonus_points"], 1)
        self.assertNotIn("student@example.com", resp.content.decode())

    def test_leaderboard_refresh_updates_scores_and_version(self):
        enrollment = Enrollment.objects.create(
            student=self.student_user,
            course=self.course,
            bonus_points=2,
        )
        old_version = self.course.leaderboard_cache_version
        resp = self.client.post(
            f"/api/courses/{self.course.slug}/leaderboard/refresh/",
            HTTP_AUTHORIZATION=f"Token {self.staff_token.key}",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["updated"])
        self.assertEqual(data["leaderboard_cache_version"], old_version + 1)
        enrollment.refresh_from_db()
        self.assertEqual(enrollment.total_score, 2)
        self.assertEqual(enrollment.position_on_leaderboard, 1)
