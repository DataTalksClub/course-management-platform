from dataclasses import dataclass
from io import StringIO
from unittest.mock import Mock, patch

import requests
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings


DATAMAILER_SETTINGS = {
    "DATAMAILER_URL": "https://datamailer.example.com",
    "DATAMAILER_API_KEY": "secret-token",
    "DATAMAILER_CLIENT": "dtc-courses",
    "DATAMAILER_AUDIENCE": "dtc-courses",
}


@dataclass(frozen=True)
class CampaignCommandMocks:
    upsert_campaign: Mock
    preview_campaign: Mock
    test_send_campaign: Mock
    queue_campaign: Mock


@dataclass(frozen=True)
class CampaignActionRunExpectation:
    mocks: CampaignCommandMocks
    out: StringIO


class DatamailerCampaignCommandTest(TestCase):
    def configure_campaign_command_mocks(self, mocks):
        mocks.upsert_campaign.return_value = {
            "campaign": {
                "external_key": "course-start-2026",
                "status": "draft",
            },
        }
        mocks.preview_campaign.return_value = {"subject": "Course starts"}
        mocks.test_send_campaign.return_value = {"queued_count": 1}
        mocks.queue_campaign.return_value = {"campaign": {"status": "queued"}}

    def run_campaign_command(self):
        out = StringIO()
        call_command(
            "datamailer_campaign",
            "course-start-2026",
            "--subject",
            "Course starts",
            "--text",
            "Hello learners",
            "--include-tag",
            "course-ml-zoomcamp",
            "--exclude-tag",
            "course-ml-zoomcamp-alumni",
            "--recipient-list-key",
            "ml-zoomcamp-2026:@e",
            "--metadata",
            "course_slug=ml-zoomcamp-2026",
            "--preview",
            "--test-send",
            "ops@example.com",
            "--queue",
            stdout=out,
        )
        return out

    def assert_campaign_upsert_payload(self, upsert_campaign):
        upsert_campaign.assert_called_once()
        self.assertEqual(upsert_campaign.call_args.args[0], "course-start-2026")
        payload = upsert_campaign.call_args.args[1]
        self.assertEqual(payload["subject"], "Course starts")
        self.assertEqual(payload["text_body"], "Hello learners")
        self.assertEqual(payload["html_body"], "")
        self.assertEqual(payload["category_tag"], "course-updates")
        self.assertEqual(payload["recipient_list_key"], "ml-zoomcamp-2026:@e")
        self.assertEqual(payload["include_tags"], ["course-ml-zoomcamp"])
        self.assertEqual(payload["exclude_tags"], ["course-ml-zoomcamp-alumni"])
        self.assertEqual(
            payload["metadata"],
            {"course_slug": "ml-zoomcamp-2026"},
        )

    def assert_campaign_actions_ran(self, expectation):
        expectation.mocks.preview_campaign.assert_called_once_with(
            "course-start-2026"
        )
        expectation.mocks.test_send_campaign.assert_called_once_with(
            "course-start-2026",
            ["ops@example.com"],
        )
        expectation.mocks.queue_campaign.assert_called_once_with(
            "course-start-2026"
        )
        self.assertIn(
            "Upserted course-start-2026: status=draft",
            expectation.out.getvalue(),
        )
        self.assertIn("queue: ok", expectation.out.getvalue())

    @override_settings(**DATAMAILER_SETTINGS)
    def test_datamailer_campaign_command_upserts_and_runs_actions(self):
        with (
            patch(
                "course_management.datamailer.client.DatamailerClient.upsert_campaign"
            ) as upsert_campaign,
            patch(
                "course_management.datamailer.client.DatamailerClient.preview_campaign"
            ) as preview_campaign,
            patch(
                "course_management.datamailer.client.DatamailerClient.test_send_campaign"
            ) as test_send_campaign,
            patch(
                "course_management.datamailer.client.DatamailerClient.queue_campaign"
            ) as queue_campaign,
        ):
            mocks = CampaignCommandMocks(
                upsert_campaign=upsert_campaign,
                preview_campaign=preview_campaign,
                test_send_campaign=test_send_campaign,
                queue_campaign=queue_campaign,
            )
            self.configure_campaign_command_mocks(mocks)

            out = self.run_campaign_command()

        self.assert_campaign_upsert_payload(upsert_campaign)
        expectation = CampaignActionRunExpectation(
            mocks=mocks,
            out=out,
        )
        self.assert_campaign_actions_ran(expectation)

    @override_settings(**DATAMAILER_SETTINGS)
    def test_datamailer_campaign_command_requires_body(self):
        with self.assertRaisesMessage(
            CommandError,
            "Provide --html, --html-file, --text, or --text-file.",
        ):
            call_command(
                "datamailer_campaign",
                "course-start-2026",
                "--subject",
                "Course starts",
            )

    @override_settings(**DATAMAILER_SETTINGS)
    def test_datamailer_campaign_command_requires_category_tag(self):
        with self.assertRaisesMessage(CommandError, "--category-tag is required."):
            call_command(
                "datamailer_campaign",
                "course-start-2026",
                "--subject",
                "Course starts",
                "--text",
                "Hello learners",
                "--category-tag",
                "",
            )

    @override_settings(**DATAMAILER_SETTINGS)
    def test_datamailer_campaign_command_rejects_queue_and_cancel(self):
        with self.assertRaisesMessage(
            CommandError,
            "--queue and --cancel cannot be used together.",
        ):
            call_command(
                "datamailer_campaign",
                "course-start-2026",
                "--subject",
                "Course starts",
                "--text",
                "Hello learners",
                "--queue",
                "--cancel",
            )

    @override_settings(**DATAMAILER_SETTINGS)
    @patch("course_management.datamailer.client.DatamailerClient.upsert_campaign")
    def test_datamailer_campaign_command_wraps_request_errors(
        self,
        upsert_campaign,
    ):
        upsert_campaign.side_effect = requests.RequestException("network error")

        with self.assertRaisesMessage(
            CommandError,
            "Datamailer campaign request failed: network error",
        ):
            call_command(
                "datamailer_campaign",
                "course-start-2026",
                "--subject",
                "Course starts",
                "--text",
                "Hello learners",
            )
