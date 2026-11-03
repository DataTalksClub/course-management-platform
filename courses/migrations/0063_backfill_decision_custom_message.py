from django.db import migrations


BATCH_SIZE = 1000
DECISION_TEMPLATES = ("application-approved", "application-rejected")


def backfill_custom_message(apps, schema_editor):
    notification = apps.get_model("courses", "ApplicationNotification")
    database = schema_editor.connection.alias
    rows = (
        notification.objects.using(database)
        .filter(template_key__in=DECISION_TEMPLATES)
        .only("id", "context")
    )
    stale_ids = []
    for row in rows.iterator(chunk_size=BATCH_SIZE):
        context = row.context or {}
        if "custom_message" in context:
            continue
        stale_ids.append(row.id)
        if len(stale_ids) >= BATCH_SIZE:
            _fill_batch(notification, database, stale_ids)
            stale_ids.clear()
    if stale_ids:
        _fill_batch(notification, database, stale_ids)


def _fill_batch(notification, database, stale_ids):
    rows = notification.objects.using(database).filter(id__in=stale_ids)
    for row in rows.iterator(chunk_size=BATCH_SIZE):
        context = dict(row.context or {})
        context["custom_message"] = ""
        row.context = context
        row.save(update_fields=["context", "updated_at"])


class Migration(migrations.Migration):
    dependencies = [
        ("courses", "0062_answer_ans_question_correct_idx_and_more"),
    ]

    operations = [
        migrations.RunPython(
            backfill_custom_message,
            migrations.RunPython.noop,
        ),
    ]
