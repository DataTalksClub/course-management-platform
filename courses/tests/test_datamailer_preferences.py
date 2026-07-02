from unittest.mock import patch

from django.test import override_settings

from course_management.datamailer.preferences import (
    get_email_preferences_for_user,
    update_email_preferences_for_user,
)

from .datamailer_status_base import (
    DATAMAILER_SETTINGS,
    DatamailerPreferenceReadTestBase,
    DatamailerPreferenceUpdateTestBase,
)


class DatamailerPreferencesTest(
    DatamailerPreferenceReadTestBase,
    DatamailerPreferenceUpdateTestBase,
):
    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.contact_preferences"
    )
    def test_get_email_preferences_for_user_reads_datamailer_categories(
        self,
        contact_preferences,
    ):
        contact_preferences.return_value = self.contact_preferences_response()
        user = self.create_student_user(email="Student@Example.com")

        result = get_email_preferences_for_user(user)

        self.assert_datamailer_preferences(result)
        self.assert_contact_preferences_read(contact_preferences)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client.DatamailerClient.update_contact_preferences"
    )
    def test_update_email_preferences_for_user_writes_datamailer_categories(
        self,
        update_contact_preferences,
    ):
        user = self.create_student_user()

        updated_preferences = self.updated_email_preferences()
        result = update_email_preferences_for_user(
            user,
            updated_preferences,
        )

        self.assertTrue(result)
        self.assert_contact_preferences_updated(update_contact_preferences)
