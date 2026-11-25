"""Record that GenMedia email 4 was sent through Relay outside cadmin.

On 2026-11-10 a script queued email campaign 4 ("Live Q&A today!") straight
in Relay, targeting ``production-ai-agents-generative-media:@approved``.
Relay reports it as sent to 851 recipients at 11:10:48 UTC, but the CMP row
stayed ``draft``, so cadmin still offered to queue it again.

The update only touches the row with that exact Relay external key and only
while it is still unqueued, so it is a no-op on databases without it and on
any row staff have already changed.
"""

from datetime import datetime, timezone

from django.db import migrations


EXTERNAL_KEY = "cmp-registration-production-ai-agents-generative-media-10ac3865"
RELAY_SENT_COUNT = 851
RELAY_SENT_AT = datetime(2026, 11, 10, 11, 10, 48, tzinfo=timezone.utc)
UNQUEUED_STATUSES = ("draft", "synced", "queue_pending")


def mark_email_campaign_queued(apps, schema_editor):
    EmailCampaign = apps.get_model("courses", "EmailCampaign")
    EmailCampaign.objects.filter(
        external_key=EXTERNAL_KEY,
        status__in=UNQUEUED_STATUSES,
    ).update(
        status="queued",
        last_recipient_count=RELAY_SENT_COUNT,
        queued_at=RELAY_SENT_AT,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("courses", "0072_genmedia_started_course_info"),
    ]

    operations = [
        migrations.RunPython(
            mark_email_campaign_queued,
            migrations.RunPython.noop,
        ),
    ]
