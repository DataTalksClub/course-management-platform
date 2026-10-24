from unittest.mock import patch

from django.test import override_settings

from courses.models import CourseRegistration
from courses.tests.registration_campaign_base import RegistrationCampaignBase


class RegistrationCampaignNotificationTests(RegistrationCampaignBase):
    @override_settings(
        RELAY_URL="https://relay.example.com",
        RELAY_API_KEY="secret-token",
        RELAY_CLIENT="dtc-courses",
        RELAY_AUDIENCE="dtc-courses",
    )
    @patch(
        "courses.views.registration.send_registration_confirmation_email"
    )
    @patch("courses.views.registration.sync_registration_to_relay")
    def test_registration_syncs_to_relay_and_sends_confirmation(
        self,
        sync_relay,
        send_confirmation,
    ):
        url = self.campaign_url()
        payload = self.registration_payload()
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                url,
                payload,
            )

        self.assertEqual(response.status_code, 200)
        registration = CourseRegistration.objects.get()
        sync_relay.assert_called_once_with(registration)
        send_confirmation.assert_called_once_with(registration)
