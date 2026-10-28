from datetime import timedelta

from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser
from courses.models import Course, CourseRegistration
from courses.registration_counts import (
    registered_count_cache_key,
    registered_people_count,
)
from courses.tests.registration_campaign_base import RegistrationCampaignBase


EMPTY_STATE_TEXT = (
    "There are no homeworks or projects available for this course yet."
)


@override_settings(
    RELAY_URL="",
    RELAY_API_KEY="",
    RELAY_CLIENT="",
    RELAY_AUDIENCE="",
)
class CourseRegisteredCountTests(RegistrationCampaignBase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.course.requires_registration_approval = True
        self.course.save(update_fields=["requires_registration_approval"])
        self.course_url = reverse("course", args=[self.course.slug])

    def create_user(self, email):
        return CustomUser.objects.create_user(
            username=email,
            email=email,
            password="test",
        )

    def create_registration(
        self,
        email,
        status=CourseRegistration.Status.PENDING,
        confirmed=False,
    ):
        return CourseRegistration.objects.create(
            campaign=self.campaign,
            course=self.course,
            email=email,
            name="Applicant",
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.DATA_ENGINEER,
            status=status,
            email_confirmed=confirmed,
        )

    def login_user(self, email):
        user = self.create_user(email)
        self.create_registration(email)
        self.client.force_login(user)
        return user

    def test_pending_applicant_sees_status_block_and_count_not_empty_state(
        self,
    ):
        self.login_user("pending@example.com")

        response = self.client.get(self.course_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your application is under review.")
        self.assertContains(
            response, "you will get access to the homeworks and projects"
        )
        self.assertContains(response, "we will email you")
        self.assertNotContains(response, EMPTY_STATE_TEXT)
        self.assertContains(response, "1 person has already registered")

    def test_pending_status_block_links_materials_only_when_present(self):
        self.login_user("pending@example.com")
        self.course.github_repo_url = (
            "https://github.com/DataTalksClub/llm-zoomcamp"
        )
        self.course.save(update_fields=["github_repo_url"])

        response = self.client.get(self.course_url)

        self.assertContains(response, "public course materials")
        self.assertContains(
            response,
            'href="https://github.com/DataTalksClub/llm-zoomcamp"',
        )

        self.course.github_repo_url = ""
        self.course.save(update_fields=["github_repo_url"])

        response = self.client.get(self.course_url)

        self.assertNotContains(response, "public course materials")
        self.assertNotContains(
            response,
            "https://github.com/DataTalksClub/llm-zoomcamp",
        )

    def test_approved_user_without_homeworks_sees_existing_empty_state(self):
        user = self.create_user("approved@example.com")
        self.create_registration(
            user.email,
            status=CourseRegistration.Status.APPROVED,
            confirmed=True,
        )
        self.client.force_login(user)

        response = self.client.get(self.course_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, EMPTY_STATE_TEXT)
        self.assertNotContains(response, "Your application is under review.")
        self.assertContains(response, "1 person has already registered")

    def test_anonymous_user_sees_registered_count_and_unchanged_empty_state(
        self,
    ):
        self.create_registration("one@example.com")
        self.create_registration(
            "two@example.com",
            status=CourseRegistration.Status.APPROVED,
            confirmed=True,
        )

        response = self.client.get(self.course_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "2 people have already registered")
        self.assertContains(response, EMPTY_STATE_TEXT)

    def test_registered_count_hidden_when_zero(self):
        response = self.client.get(self.course_url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "already registered")

    def test_count_matches_digest_record_definition(self):
        from course_management.relay.registration_digest import (
            collect_digest_registrations,
        )

        self.create_registration("pending-unconfirmed@example.com")
        self.create_registration(
            "approved-confirmed@example.com",
            status=CourseRegistration.Status.APPROVED,
            confirmed=True,
        )
        self.create_registration(
            "rejected-confirmed@example.com",
            status=CourseRegistration.Status.REJECTED,
            confirmed=True,
        )
        other_course = Course.objects.create(
            slug="other-course",
            title="Other Course",
            description="Other course",
        )
        CourseRegistration.objects.create(
            campaign=self.campaign,
            course=other_course,
            email="other-course@example.com",
            name="Other Applicant",
            country="Germany",
            region="Europe",
            role=CourseRegistration.Role.DATA_ENGINEER,
        )

        now = timezone.now()
        digest_rows = collect_digest_registrations(
            now - timedelta(days=1),
            now + timedelta(seconds=1),
        )
        digest_course_count = sum(
            1 for row in digest_rows if row.course_id == self.course.pk
        )

        self.assertEqual(digest_course_count, 3)
        self.assertEqual(
            registered_people_count(self.course),
            digest_course_count,
        )
        self.assertEqual(
            registered_people_count(self.course),
            CourseRegistration.objects.filter(course=self.course).count(),
        )

    def test_count_is_cached_across_calls(self):
        self.create_registration("cached@example.com")

        self.assertEqual(registered_people_count(self.course), 1)

        with self.assertNumQueries(0):
            self.assertEqual(registered_people_count(self.course), 1)

        cache.delete(registered_count_cache_key(self.course))

        with self.assertNumQueries(1):
            self.assertEqual(registered_people_count(self.course), 1)
