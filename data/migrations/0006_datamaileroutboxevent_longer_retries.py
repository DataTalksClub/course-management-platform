from django.db import migrations, models


def bump_in_flight_max_attempts(apps, schema_editor):
    datamailer_outbox_event = apps.get_model(
        "data",
        "DatamailerOutboxEvent",
    )
    datamailer_outbox_event.objects.filter(
        status__in=["pending", "retrying", "processing"],
    ).update(max_attempts=24)


class Migration(migrations.Migration):

    dependencies = [
        ("data", "0005_datamailersendaudit"),
    ]

    operations = [
        migrations.AlterField(
            model_name="datamaileroutboxevent",
            name="max_attempts",
            field=models.PositiveIntegerField(default=24),
        ),
        migrations.RunPython(
            bump_in_flight_max_attempts,
            migrations.RunPython.noop,
        ),
    ]
