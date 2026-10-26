"""Production AI program outline: label items Module 1-4 instead of Week 1-4 (t1515u)."""

from django.db import migrations

SLUG = "production-ai-agents-generative-media"
TITLES = [
    "Make it work",
    "Make it intelligent",
    "Make it scale",
    "Make it production-ready",
]


def _relabel(apps, old, new):
    RegistrationCampaign = apps.get_model("courses", "RegistrationCampaign")
    campaign = RegistrationCampaign.objects.filter(slug=SLUG).first()
    if not campaign or not campaign.marketing_markdown:
        return
    text = campaign.marketing_markdown
    for n, title in enumerate(TITLES, start=1):
        text = text.replace(f"**{old} {n} - {title}.**", f"**{new} {n} - {title}.**")
    if text != campaign.marketing_markdown:
        campaign.marketing_markdown = text
        campaign.save(update_fields=["marketing_markdown"])


def forwards(apps, schema_editor):
    _relabel(apps, "Week", "Module")


def backwards(apps, schema_editor):
    _relabel(apps, "Module", "Week")


class Migration(migrations.Migration):
    dependencies = [
        ("courses", "0053_registrationdigestsend"),
    ]
    operations = [
        migrations.RunPython(forwards, backwards),
    ]
