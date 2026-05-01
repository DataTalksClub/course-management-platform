from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_backfill_certificate_name_from_enrollment"),
        ("courses", "0029_enrollment_display_public_profile"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="enrollment",
            name="about_me",
        ),
        migrations.RemoveField(
            model_name="enrollment",
            name="github_url",
        ),
        migrations.RemoveField(
            model_name="enrollment",
            name="linkedin_url",
        ),
        migrations.RemoveField(
            model_name="enrollment",
            name="personal_website_url",
        ),
    ]
