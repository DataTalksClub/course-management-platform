"""Seed the digest worker state so a fresh deploy does not alarm before the first run."""

from django.db import migrations
from django.utils import timezone


def seed_digest_job_state(apps, schema_editor):
    CmpJobState = apps.get_model("data", "CmpJobState")
    CmpJobState.objects.get_or_create(
        job="digest",
        defaults={"last_success_at": timezone.now()},
    )


class Migration(migrations.Migration):
    dependencies = [
        ("data", "0007_cmpjobstate"),
    ]

    operations = [
        migrations.RunPython(
            seed_digest_job_state,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
