from unittest.mock import patch

from django.test import override_settings

from courses.models.course import CourseRegistration
from courses.tests.datamailer_recipient_lists_base import (
    RELAY_SETTINGS,
    DatamailerRecipientListCommandTestBase,
)
from courses.tests.test_datamailer_recipient_lists import (
    run_recipient_list_command,
)

SETTINGS = RELAY_SETTINGS | {"PUBLIC_BASE_URL": "https://courses.datatalks.club"}


class ApprovedRegistrationsListTest(DatamailerRecipientListCommandTestBase):
    @override_settings(**SETTINGS)
    @patch(
        "course_management.datamailer.client_recipient_lists.DatamailerRecipientListMemberClient.bulk_upsert"
    )
    def test_approved_list_has_only_approved_with_own_invite_url(
        self, bulk_upsert
    ):
        bulk_upsert.return_value = {"recipient_list": {"active_member_count": 2}}
        first = self.create_registration(
            status=CourseRegistration.Status.APPROVED
        )
        campaign, course = first.campaign, first.course
        second = CourseRegistration.objects.create(
            campaign=campaign, course=course, email="two@example.com",
            name="Two", status=CourseRegistration.Status.APPROVED,
        )
        CourseRegistration.objects.create(
            campaign=campaign, course=course, email="pending@example.com",
            name="Pending", status=CourseRegistration.Status.PENDING,
        )

        run_recipient_list_command(
            "approved-registrations", "--course-slug", campaign.slug
        )

        bulk_upsert.assert_called_once()
        list_key, payload = bulk_upsert.call_args.args
        self.assertEqual(list_key, f"{course.slug}:@approved")
        self.assertEqual(payload["list"]["type"], "approved-registrants")
        self.assertNotIn("merge_vars", payload["list"]["metadata"])
        invites = {
            m["email"]: m["metadata"]["merge_vars"]["invite_url"]
            for m in payload["members"]
        }
        self.assertEqual(
            invites,
            {
                "student@example.com": "https://courses.datatalks.club/register/"
                f"{campaign.slug}/?ref={first.pk}",
                "two@example.com": "https://courses.datatalks.club/register/"
                f"{campaign.slug}/?ref={second.pk}",
            },
        )
