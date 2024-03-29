# Generated by Django 4.2.10 on 2024-02-13 15:35

from django.db import migrations, models

from courses.models import Course

def set_first_homework_scored_true_for_existing_records(apps, schema_editor):
    Course.objects.all().update(first_homework_scored=True)

class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0005_update_answers_with_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="course",
            name="first_homework_scored",
            field=models.BooleanField(
                help_text="Whether the first homework has been scored. We use that for deciding whether to show the leaderboard.",
                default=False,
            ),
        ),
        migrations.RunPython(set_first_homework_scored_true_for_existing_records),
    ]
