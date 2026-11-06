"""The genmedia course is curated into every other course's suggestions."""

import importlib

from django.apps import apps

from courses.models import RegistrationCampaign
from courses.tests.registration_campaign_base import RegistrationCampaignBase

migration = importlib.import_module(
    "courses.migrations.0067_genmedia_cross_sell_everywhere"
)
GENMEDIA_CAMPAIGN_SLUG = migration.GENMEDIA_CAMPAIGN_SLUG
add_genmedia_to_suggestions = migration.add_genmedia_to_suggestions


class GenmediaCrossSellEverywhereTests(RegistrationCampaignBase):
    def test_migration_curates_genmedia_into_all_active_campaigns(self):
        genmedia = RegistrationCampaign.objects.get(
            slug=GENMEDIA_CAMPAIGN_SLUG
        )
        # Base campaign (llm-zoomcamp) starts uncurated.
        self.assertNotIn(
            genmedia, self.campaign.suggested_campaigns.all()
        )

        add_genmedia_to_suggestions(apps, None)
        # Idempotent: safe to run twice (e.g. re-deploys).
        add_genmedia_to_suggestions(apps, None)

        self.campaign.refresh_from_db()
        self.assertIn(genmedia, self.campaign.suggested_campaigns.all())
        self.assertNotIn(
            genmedia, genmedia.suggested_campaigns.all()
        )
