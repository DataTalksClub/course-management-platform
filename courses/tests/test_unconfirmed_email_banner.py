from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from courses.models.course import (
    Course,
    CourseRegistration,
    RegistrationCampaign,
)
from courses.registration_confirmation import (
    EMAIL_CONFIRMATION_MAX_RESENDS,
    management_token,
)

User = get_user_model()


class UnconfirmedEmailBannerTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="student1",
            email="student1@example.com",
            password="password123",
        )
        self.other_user = User.objects.create_user(
            username="student2",
            email="student2@example.com",
            password="password123",
        )
        self.course = Course.objects.create(
            slug="de-zoomcamp-2026",
            title="Data Engineering Zoomcamp 2026",
            description="DE course",
            visible=True,
        )
        self.other_course = Course.objects.create(
            slug="ml-zoomcamp-2026",
            title="ML Zoomcamp 2026",
            description="ML course",
            visible=True,
        )
        self.campaign = RegistrationCampaign.objects.create(
            slug="de-zoomcamp-2026",
            title="DE Zoomcamp 2026",
            current_course=self.course,
            is_active=True,
        )
        self.other_campaign = RegistrationCampaign.objects.create(
            slug="ml-zoomcamp-2026",
            title="ML Zoomcamp 2026",
            current_course=self.other_course,
            is_active=True,
        )

    def _create_registration(self, **overrides):
        defaults = {
            "campaign": self.campaign,
            "course": self.course,
            "user": self.user,
            "email": self.user.email,
            "name": "Student One",
            "country": "Germany",
            "region": "Europe",
            "role": CourseRegistration.Role.DATA_ENGINEER,
            "email_confirmed": False,
            "email_confirmation_token": "confirm-token-1",
            "email_confirmation_sent_at": timezone.now()
            - timedelta(minutes=10),
            "email_confirmation_resend_count": 1,
        }
        defaults.update(overrides)
        return CourseRegistration.objects.create(**defaults)

    def test_course_page_shows_banner_for_unconfirmed_user_fk(self):
        self._create_registration()
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("course", kwargs={"course_slug": self.course.slug})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-unconfirmed-registration-banner")
        self.assertContains(response, "student1@example.com")
        self.assertContains(response, "is not confirmed yet")
        self.assertContains(response, "Resend verification email")
        self.assertContains(
            response, reverse("registration_confirmation_resend")
        )

    def test_course_page_shows_banner_when_matched_by_email_only(self):
        self._create_registration(user=None, email="Student1@Example.com")
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("course", kwargs={"course_slug": self.course.slug})
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-unconfirmed-registration-banner")
        self.assertContains(response, "Student1@Example.com")

    def test_course_page_hides_banner_for_confirmed_anonymous_and_other_user(
        self,
    ):
        registration = self._create_registration()
        course_url = reverse("course", kwargs={"course_slug": self.course.slug})

        # Anonymous user does not see the banner.
        anon_response = self.client.get(course_url)
        self.assertNotContains(
            anon_response, "data-unconfirmed-registration-banner"
        )

        # Different logged-in user does not see the banner.
        self.client.force_login(self.other_user)
        other_response = self.client.get(course_url)
        self.assertNotContains(
            other_response, "data-unconfirmed-registration-banner"
        )

        # Confirming via confirmation link removes the banner for the owner.
        self.client.force_login(self.user)
        confirm_response = self.client.get(
            reverse(
                "registration_confirm",
                kwargs={"token": registration.email_confirmation_token},
            )
        )
        self.assertEqual(confirm_response.status_code, 200)

        after_confirm = self.client.get(course_url)
        self.assertNotContains(
            after_confirm, "data-unconfirmed-registration-banner"
        )

    def test_dashboard_shows_one_banner_per_unconfirmed_registration(self):
        reg1 = self._create_registration(
            email_confirmation_token="confirm-token-a"
        )
        self._create_registration(
            campaign=self.other_campaign,
            course=self.other_course,
            email_confirmation_token="confirm-token-b",
        )
        dashboard_url = reverse("course_list")

        # Anonymous user sees no banners.
        anon_response = self.client.get(dashboard_url)
        self.assertNotContains(
            anon_response, "data-unconfirmed-registration-banner"
        )

        # Other user sees no banners.
        self.client.force_login(self.other_user)
        other_response = self.client.get(dashboard_url)
        self.assertNotContains(
            other_response, "data-unconfirmed-registration-banner"
        )

        # Owner sees both unconfirmed banners.
        self.client.force_login(self.user)
        response = self.client.get(dashboard_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, "data-unconfirmed-registration-banner", count=2
        )
        self.assertContains(response, self.course.title)
        self.assertContains(response, self.other_course.title)

        # Confirming one leaves only the other.
        self.client.get(
            reverse(
                "registration_confirm",
                kwargs={"token": reg1.email_confirmation_token},
            )
        )
        after_one = self.client.get(dashboard_url)
        self.assertContains(
            after_one, "data-unconfirmed-registration-banner", count=1
        )
        self.assertNotContains(
            after_one,
            f"is not confirmed yet for {self.course.title}",
        )

    @patch(
        "courses.views.registration_confirmation.sync_registration_to_relay"
    )
    @patch(
        "courses.views.registration_confirmation.send_registration_confirmation_email"
    )
    def test_resend_from_banner_success_returns_to_page_with_message(
        self, send_mock, sync_mock
    ):
        send_mock.return_value = {"id": "msg-123"}
        registration = self._create_registration()
        course_url = reverse("course", kwargs={"course_slug": self.course.slug})
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("registration_confirmation_resend"),
            {
                "token": management_token(registration),
                "next": course_url,
            },
            follow=True,
        )

        self.assertRedirects(response, course_url)
        self.assertContains(
            response,
            f"Confirmation email sent to {registration.email}",
        )
        send_mock.assert_called_once_with(registration)
        sync_mock.assert_called_once_with(registration)
        registration.refresh_from_db()
        self.assertNotEqual(
            registration.email_confirmation_token, "confirm-token-1"
        )

    def test_resend_from_banner_rate_limited_shows_wait_time(self):
        registration = self._create_registration(
            email_confirmation_sent_at=timezone.now() - timedelta(seconds=15),
        )
        dashboard_url = reverse("course_list")
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("registration_confirmation_resend"),
            {
                "token": management_token(registration),
                "next": dashboard_url,
            },
            follow=True,
        )

        self.assertRedirects(response, dashboard_url)
        self.assertContains(response, "wait a minute")
        self.assertContains(response, "try again in ")

    def test_resend_from_banner_too_many_resends_shows_error(self):
        registration = self._create_registration(
            email_confirmation_resend_count=EMAIL_CONFIRMATION_MAX_RESENDS,
        )
        course_url = reverse("course", kwargs={"course_slug": self.course.slug})
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("registration_confirmation_resend"),
            {
                "token": management_token(registration),
                "next": course_url,
            },
            follow=True,
        )

        self.assertRedirects(response, course_url)
        self.assertContains(response, "Too many confirmation emails")

    @patch(
        "courses.views.registration_confirmation.sync_registration_to_relay"
    )
    @patch(
        "courses.views.registration_confirmation.send_registration_confirmation_email"
    )
    def test_resend_send_failure_shows_visible_error_with_and_without_next(
        self, send_mock, sync_mock
    ):
        send_mock.return_value = None
        registration = self._create_registration()
        course_url = reverse("course", kwargs={"course_slug": self.course.slug})
        self.client.force_login(self.user)

        # With next: redirects back with visible error message.
        response_with_next = self.client.post(
            reverse("registration_confirmation_resend"),
            {
                "token": management_token(registration),
                "next": course_url,
            },
            follow=True,
        )
        self.assertRedirects(response_with_next, course_url)
        self.assertContains(
            response_with_next,
            f"Could not send the confirmation email to {registration.email}",
        )

        # Without next (after cooldown expires): status page shows error, not "sent".
        registration.email_confirmation_sent_at = timezone.now() - timedelta(
            minutes=5
        )
        registration.save(update_fields=["email_confirmation_sent_at"])
        response_without_next = self.client.post(
            reverse("registration_confirmation_resend"),
            {"token": management_token(registration)},
        )
        self.assertEqual(response_without_next.status_code, 200)
        self.assertNotContains(response_without_next, "Confirmation email sent")
        self.assertContains(
            response_without_next,
            f"Could not send the confirmation email to {registration.email}",
        )
