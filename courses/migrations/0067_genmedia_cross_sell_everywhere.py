"""Recommend the genmedia course after every other course registration.

Adds the production-ai-agents-generative-media campaign to the curated
``suggested_campaigns`` of every other active campaign, so it is always
in the suggestion set (curated entries sort before the automatic
fallback). Idempotent; reverse is a no-op. Per-course curators can still
remove it in cadmin afterwards.
"""

from django.db import migrations


GENMEDIA_CAMPAIGN_SLUG = "production-ai-agents-generative-media"


def add_genmedia_to_suggestions(apps, schema_editor):
    RegistrationCampaign = apps.get_model("courses", "RegistrationCampaign")
    try:
        genmedia = RegistrationCampaign.objects.get(
            slug=GENMEDIA_CAMPAIGN_SLUG
        )
    except RegistrationCampaign.DoesNotExist:
        return
    for campaign in RegistrationCampaign.objects.filter(is_active=True).exclude(
        pk=genmedia.pk
    ):
        campaign.suggested_campaigns.add(genmedia)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("courses", "0066_alter_referralreward_points"),
    ]

    operations = [
        migrations.RunPython(add_genmedia_to_suggestions, noop),
    ]
