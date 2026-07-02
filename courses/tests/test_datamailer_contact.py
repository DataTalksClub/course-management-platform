from unittest.mock import patch

import requests
from django.test import override_settings

from accounts.models import CustomUser
from course_management.datamailer.keys import contact_tags_for_course
from course_management.datamailer.payloads.base import (
    contact_payload_for_user,
)
from course_management.datamailer.sync.contacts import sync_contact
from courses.models import Course
from courses.tests.datamailer_contact_base import (
    DATAMAILER_SETTINGS,
    DatamailerContactBase,
)


class DatamailerContactTest(DatamailerContactBase):
    @override_settings(**DATAMAILER_SETTINGS)
    def test_contact_payload_includes_course_subscription_data(self):
        user, course = self.create_contact_payload_fixture()

        payload = contact_payload_for_user(user, course=course)

        self.assert_course_subscription_contact_payload(payload)

    def test_contact_tags_for_course_without_trailing_year(self):
        course = Course(
            slug="ml-zoomcamp",
            title="ML Zoomcamp",
            description="Machine learning",
        )

        tags = contact_tags_for_course(course)
        expected_tags = []
        expected_tags.append("course-ml-zoomcamp")
        expected_tags.append("course-cohort-ml-zoomcamp")
        self.assertEqual(tags, expected_tags)

    @override_settings(**DATAMAILER_SETTINGS)
    @patch(
        "course_management.datamailer.client_contacts.DatamailerContactClient.upsert_contact"
    )
    def test_sync_contact_logs_and_continues_on_api_failure(
        self, upsert
    ):
        upsert.side_effect = requests.RequestException("network error")
        user = CustomUser.objects.create(email="student@example.com")

        sync_contact(user)

        upsert.assert_called_once()

    @override_settings(**DATAMAILER_SETTINGS, DATAMAILER_STRICT=True)
    @patch(
        "course_management.datamailer.client_contacts.DatamailerContactClient.upsert_contact"
    )
    def test_sync_contact_can_be_strict(self, upsert):
        upsert.side_effect = requests.RequestException("network error")
        user = CustomUser.objects.create(email="student@example.com")

        with self.assertRaises(requests.RequestException):
            sync_contact(user)
