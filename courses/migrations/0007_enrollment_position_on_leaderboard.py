# Generated by Django 4.2.10 on 2024-02-13 16:43

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0006_course_first_homework_scored"),
    ]

    operations = [
        migrations.AddField(
            model_name="enrollment",
            name="position_on_leaderboard",
            field=models.IntegerField(blank=True, default=0, null=True),
        ),
    ]
