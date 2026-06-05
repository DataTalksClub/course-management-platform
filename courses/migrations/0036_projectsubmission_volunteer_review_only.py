from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0035_projectvote"),
    ]

    operations = [
        migrations.AddField(
            model_name="projectsubmission",
            name="volunteer_review_only",
            field=models.BooleanField(default=False),
        ),
    ]
