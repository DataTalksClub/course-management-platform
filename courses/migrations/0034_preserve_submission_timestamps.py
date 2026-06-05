import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("courses", "0033_projectsubmission_faq_contribution_url_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="projectsubmission",
            name="submitted_at",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AlterField(
            model_name="submission",
            name="submitted_at",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
    ]
