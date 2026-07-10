from unittest.mock import patch

from django.test import override_settings

from accounts.models import CustomUser
from data.models import DatamailerOutboxEvent
from course_management.datamailer.sync.contacts import (
    erase_contact_from_datamailer,
)
from courses.tests.datamailer_outbox_base import (
    DATAMAILER_SETTINGS,
    DatamailerOutboxTestBase,
)


class DatamailerOutboxContactTest(DatamailerOutboxTestBase):
    @override_settings(**DATAMAILER_SETTINGS)
    @patch("course_management.datamailer.client_contacts.DatamailerContactClient.erase_contact")
    def test_erase_contact_enqueues_outbox_event(self, erase_contact):
        user = CustomUser.objects.create_user(
            username="student",
            email="Student@Example.com",
        )

        erase_contact_from_datamailer(user)

        erase_contact.assert_called_once_with("student@example.com")
        event = DatamailerOutboxEvent.objects.get()
        self.assert_erase_contact_outbox_event_for_user(event, user)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch("course_management.datamailer.client_contacts.DatamailerContactClient.erase_contact")
    def test_erase_contact_enqueues_outbox_event_for_email(
        self, erase_contact
    ):
        erase_contact_from_datamailer(email=" Student@Example.com ")

        erase_contact.assert_called_once_with("student@example.com")
        event = DatamailerOutboxEvent.objects.get()
        self.assert_erase_contact_outbox_event_for_email(event)
