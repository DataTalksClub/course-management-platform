from django.db import migrations

from courses.validators.custom_url_validators import (
    is_github_repository_url,
)


BATCH_SIZE = 1000


def flag_existing_invalid_project_submissions(apps, schema_editor):
    project_submission = apps.get_model("courses", "ProjectSubmission")
    database = schema_editor.connection.alias
    invalid_ids = []

    submissions = project_submission.objects.using(database).only(
        "id", "github_link"
    )
    for submission in submissions.iterator(chunk_size=BATCH_SIZE):
        if is_github_repository_url(submission.github_link):
            continue

        invalid_ids.append(submission.id)
        if len(invalid_ids) >= BATCH_SIZE:
            project_submission.objects.using(database).filter(
                id__in=invalid_ids
            ).update(invalid_repository_flagged=True)
            invalid_ids.clear()

    if invalid_ids:
        project_submission.objects.using(database).filter(
            id__in=invalid_ids
        ).update(invalid_repository_flagged=True)


class Migration(migrations.Migration):
    dependencies = [
        ("courses", "0060_project_submission_invalid_repository_flag"),
    ]

    operations = [
        migrations.RunPython(
            flag_existing_invalid_project_submissions,
            migrations.RunPython.noop,
        ),
    ]
