import importlib
from datetime import datetime, timezone

from django.apps import apps
from django.test import TestCase

from courses.models import EmailCampaign, RegistrationCampaign


migration = importlib.import_module(
    "courses.migrations.0073_reconcile_genmedia_email_campaign_4"
)


class ReconcileGenmediaEmailCampaignTest(TestCase):
    def setUp(self):
        self.campaign = RegistrationCampaign.objects.get_or_create(
            slug="production-ai-agents-generative-media",
            defaults={"title": "GenMedia"},
        )[0]

    def email(self, external_key, status="draft"):
        email = EmailCampaign(
            registration_campaign=self.campaign,
            subject="Live Q&A today!",
            body_markdown="b",
            status=status,
        )
        email.external_key = external_key
        email.save()
        return email

    def test_marks_relay_sent_campaign_queued(self):
        email = self.email(migration.EXTERNAL_KEY)

        migration.mark_email_campaign_queued(apps, None)

        email.refresh_from_db()
        self.assertEqual(email.status, EmailCampaign.Status.QUEUED)
        self.assertEqual(email.last_recipient_count, 851)
        self.assertEqual(
            email.queued_at,
            datetime(2026, 11, 10, 11, 10, 48, tzinfo=timezone.utc),
        )

    def test_leaves_other_campaigns_alone(self):
        other = self.email(
            "cmp-registration-production-ai-agents-generative-media-e19dfb7b"
        )

        migration.mark_email_campaign_queued(apps, None)

        other.refresh_from_db()
        self.assertEqual(other.status, EmailCampaign.Status.DRAFT)
        self.assertIsNone(other.queued_at)

    def test_keeps_cancelled_campaign_cancelled(self):
        email = self.email(migration.EXTERNAL_KEY, status="cancelled")

        migration.mark_email_campaign_queued(apps, None)

        email.refresh_from_db()
        self.assertEqual(email.status, EmailCampaign.Status.CANCELLED)
