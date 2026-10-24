# Preserve legacy registration behavior without sending any emails.
# This grandfathering does not claim legacy addresses were verified.
# Token-bearing registrations must remain pending if the function is replayed.

from django.db import migrations
from django.utils import timezone


def mark_existing_registrations_confirmed(apps, schema_editor):
    CourseRegistration = apps.get_model("courses", "CourseRegistration")
    now = timezone.now()
    CourseRegistration.objects.using(schema_editor.connection.alias if schema_editor else "default").filter(
        email_confirmed=False, email_confirmation_token__isnull=True
    ).update(
        email_confirmed=True,
        email_confirmation_confirmed_at=now,
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('courses', '0051_registration_email_confirmation'),
    ]

    operations = [
        migrations.RunPython(
            mark_existing_registrations_confirmed,
            reverse_code=noop_reverse,
            elidable=True,
        ),
    ]
