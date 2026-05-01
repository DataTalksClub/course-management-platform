from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("courses", "0028_leaderboardcomplaint"),
    ]

    operations = [
        migrations.AddField(
            model_name="enrollment",
            name="display_public_profile",
            field=models.BooleanField(default=False),
        ),
    ]
